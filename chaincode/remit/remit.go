package main

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// Org roles. Adjust to the MSP IDs of your Drunix network
// (CitiOrg = Org1MSP, NPCIOrg = Org2MSP on the sample two-org network).
const (
	RemitterMSP = "Org1MSP" // remitting bank / FX provider
	PayoutMSP   = "Org2MSP" // NPCI-side payout rail (UPI)
)

// Policy constants enforced by every endorsing peer.
const (
	RiskHoldThreshold      = 60
	RiskBlockThreshold     = 85
	MinNameMatchScore      = 70
	DailyBeneficiaryCapPaise int64 = 500000000 // Rs 50,00,000 inbound per beneficiary per UTC day (demo policy)
	maxQuoteValiditySecs   int64 = 900
)

// Status values of the remittance state machine.
const (
	StCreated    = "CREATED"
	StQuoted     = "QUOTED"
	StScreened   = "SCREENED"
	StHeld       = "HELD"
	StBlocked    = "BLOCKED"
	StVerified   = "VERIFIED"
	StBenRej     = "BENEFICIARY_REJECTED"
	StFunded     = "FUNDED"
	StExpired    = "EXPIRED"
	StSubmitted  = "PAYOUT_SUBMITTED"
	StSettled    = "SETTLED"
	StFailed     = "FAILED"
	StRefunded   = "REFUNDED"
)

var allowedPurposes = map[string]bool{
	"FAMILY_MAINTENANCE": true, "EDUCATION": true, "MEDICAL": true,
	"GIFT": true, "INVESTMENT": true, "TRAVEL": true,
}

// TrailEntry is an in-state audit line; full history is also available from the ledger.
type TrailEntry struct {
	Step   string `json:"step"`
	Status string `json:"status"`
	Org    string `json:"org"`
	TxID   string `json:"txId"`
	TS     int64  `json:"ts"`
}

// Remittance holds NO personal data: sender and beneficiary are salted hashes.
type Remittance struct {
	DocType         string       `json:"docType"`
	ID              string       `json:"id"`
	Corridor        string       `json:"corridor"`
	SenderHash      string       `json:"senderHash"`
	BeneficiaryHash string       `json:"beneficiaryHash"`
	Purpose         string       `json:"purpose"`
	Status          string       `json:"status"`
	Quote           *Quote       `json:"quote,omitempty"`
	RiskScore       int          `json:"riskScore"`
	ReasonCodes     []string     `json:"reasonCodes"`
	NameMatchScore  int          `json:"nameMatchScore"`
	FundingRef      string       `json:"fundingRef,omitempty"`
	PayoutRef       string       `json:"payoutRef,omitempty"`
	UPIRef          string       `json:"upiRef,omitempty"`
	RefundRef       string       `json:"refundRef,omitempty"`
	FailReason      string       `json:"failReason,omitempty"`
	Funded          bool         `json:"funded"`
	CreatedAt       int64        `json:"createdAt"`
	UpdatedAt       int64        `json:"updatedAt"`
	Trail           []TrailEntry `json:"trail"`
}

type HistoryEntry struct {
	TxID      string `json:"txId"`
	Timestamp string `json:"timestamp"`
	IsDelete  bool   `json:"isDelete"`
	Value     string `json:"value"`
}

type RemitContract struct {
	contractapi.Contract
}

// ---------- helpers ----------

func key(id string) string { return "REM_" + id }

func requireMSP(ctx contractapi.TransactionContextInterface, want string) error {
	got, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("read caller MSP: %w", err)
	}
	if got != want {
		return fmt.Errorf("caller org %s not permitted; %s required", got, want)
	}
	return nil
}

func txNow(ctx contractapi.TransactionContextInterface) (int64, error) {
	ts, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return 0, err
	}
	return ts.Seconds, nil // deterministic across peers, never time.Now()
}

func load(ctx contractapi.TransactionContextInterface, id string) (*Remittance, error) {
	b, err := ctx.GetStub().GetState(key(id))
	if err != nil {
		return nil, err
	}
	if b == nil {
		return nil, fmt.Errorf("remittance %s not found", id)
	}
	var r Remittance
	if err := json.Unmarshal(b, &r); err != nil {
		return nil, err
	}
	return &r, nil
}

func requireStatus(r *Remittance, allowed ...string) error {
	for _, s := range allowed {
		if r.Status == s {
			return nil
		}
	}
	return fmt.Errorf("remittance %s is %s; expected one of %v", r.ID, r.Status, allowed)
}

func save(ctx contractapi.TransactionContextInterface, r *Remittance, step, status string) error {
	msp, _ := ctx.GetClientIdentity().GetMSPID()
	now, err := txNow(ctx)
	if err != nil {
		return err
	}
	r.Status = status
	r.UpdatedAt = now
	r.Trail = append(r.Trail, TrailEntry{Step: step, Status: status, Org: msp, TxID: ctx.GetStub().GetTxID(), TS: now})
	b, err := json.Marshal(r)
	if err != nil {
		return err
	}
	if err := ctx.GetStub().PutState(key(r.ID), b); err != nil {
		return err
	}
	ev, _ := json.Marshal(map[string]string{"id": r.ID, "status": status, "step": step})
	return ctx.GetStub().SetEvent("RemittanceStatusChanged", ev)
}

func velocityKey(benHash string, now int64) string {
	return "VEL_" + benHash + "_" + time.Unix(now, 0).UTC().Format("20060102")
}

func readVelocity(ctx contractapi.TransactionContextInterface, k string) (int64, error) {
	b, err := ctx.GetStub().GetState(k)
	if err != nil || b == nil {
		return 0, err
	}
	var v int64
	if err := json.Unmarshal(b, &v); err != nil {
		return 0, err
	}
	return v, nil
}

func writeVelocity(ctx contractapi.TransactionContextInterface, k string, v int64) error {
	if v < 0 {
		v = 0
	}
	b, _ := json.Marshal(v)
	return ctx.GetStub().PutState(k, b)
}

// ---------- transactions ----------

// CreateRemittance registers a remittance. Only the remitting bank may call it.
func (c *RemitContract) CreateRemittance(ctx contractapi.TransactionContextInterface,
	id, corridor, senderHash, beneficiaryHash, purpose string) error {
	if err := requireMSP(ctx, RemitterMSP); err != nil {
		return err
	}
	if id == "" || corridor == "" || senderHash == "" || beneficiaryHash == "" {
		return fmt.Errorf("id, corridor, senderHash and beneficiaryHash are required")
	}
	if !allowedPurposes[purpose] {
		return fmt.Errorf("purpose %q not allowed", purpose)
	}
	if b, err := ctx.GetStub().GetState(key(id)); err != nil {
		return err
	} else if b != nil {
		return fmt.Errorf("remittance %s already exists", id)
	}
	now, err := txNow(ctx)
	if err != nil {
		return err
	}
	r := &Remittance{DocType: "remittance", ID: id, Corridor: corridor, SenderHash: senderHash,
		BeneficiaryHash: beneficiaryHash, Purpose: purpose, CreatedAt: now, ReasonCodes: []string{}}
	return save(ctx, r, "CREATE", StCreated)
}

// LockQuote fixes the FX rate and every fee. The receive amount is computed here,
// on-chain, so the sender sees the exact figure the payout leg must honour.
func (c *RemitContract) LockQuote(ctx contractapi.TransactionContextInterface,
	id, sendCcy string, sendAmountMinor, midRateMicro, spreadBps, feeFlatMinor, feeBps, validitySecs int64) error {
	if err := requireMSP(ctx, RemitterMSP); err != nil {
		return err
	}
	r, err := load(ctx, id)
	if err != nil {
		return err
	}
	if err := requireStatus(r, StCreated); err != nil {
		return err
	}
	if validitySecs <= 0 || validitySecs > maxQuoteValiditySecs {
		return fmt.Errorf("validity must be 1..%d seconds", maxQuoteValiditySecs)
	}
	now, err := txNow(ctx)
	if err != nil {
		return err
	}
	q, err := ComputeQuote(sendCcy, sendAmountMinor, midRateMicro, spreadBps, feeFlatMinor, feeBps, now+validitySecs)
	if err != nil {
		return err
	}
	r.Quote = q
	return save(ctx, r, "LOCK_QUOTE", StQuoted)
}

// RecordScreening stores the risk decision. Thresholds are enforced here, so the
// off-chain AI can score but cannot override policy.
func (c *RemitContract) RecordScreening(ctx contractapi.TransactionContextInterface,
	id string, riskScore int, sanctionsHit bool, reasonCodes string) error {
	if err := requireMSP(ctx, RemitterMSP); err != nil {
		return err
	}
	r, err := load(ctx, id)
	if err != nil {
		return err
	}
	if err := requireStatus(r, StQuoted); err != nil {
		return err
	}
	if riskScore < 0 || riskScore > 100 {
		return fmt.Errorf("riskScore must be 0..100")
	}
	r.RiskScore = riskScore
	r.ReasonCodes = []string{}
	if reasonCodes != "" {
		r.ReasonCodes = strings.Split(reasonCodes, ",")
	}
	if sanctionsHit || riskScore >= RiskBlockThreshold {
		if sanctionsHit {
			r.ReasonCodes = append(r.ReasonCodes, "SANCTIONS_HIT")
		}
		return save(ctx, r, "SCREEN", StBlocked)
	}
	now, err := txNow(ctx)
	if err != nil {
		return err
	}
	used, err := readVelocity(ctx, velocityKey(r.BeneficiaryHash, now))
	if err != nil {
		return err
	}
	if used+r.Quote.ReceivePaise > DailyBeneficiaryCapPaise {
		r.ReasonCodes = append(r.ReasonCodes, "DAILY_CAP_EXCEEDED")
		return save(ctx, r, "SCREEN", StHeld)
	}
	if riskScore >= RiskHoldThreshold {
		return save(ctx, r, "SCREEN", StHeld)
	}
	return save(ctx, r, "SCREEN", StScreened)
}

// ReviewHold is the maker-checker step for held remittances (compliance officer at the remitting bank).
func (c *RemitContract) ReviewHold(ctx contractapi.TransactionContextInterface,
	id string, approve bool, note string) error {
	if err := requireMSP(ctx, RemitterMSP); err != nil {
		return err
	}
	r, err := load(ctx, id)
	if err != nil {
		return err
	}
	if err := requireStatus(r, StHeld); err != nil {
		return err
	}
	if approve {
		return save(ctx, r, "REVIEW_APPROVE", StScreened)
	}
	r.FailReason = note
	return save(ctx, r, "REVIEW_REJECT", StBlocked)
}

// VerifyBeneficiary is called by the payout org after a name-match against the UPI address.
func (c *RemitContract) VerifyBeneficiary(ctx contractapi.TransactionContextInterface,
	id string, matchScore int) error {
	if err := requireMSP(ctx, PayoutMSP); err != nil {
		return err
	}
	r, err := load(ctx, id)
	if err != nil {
		return err
	}
	if err := requireStatus(r, StScreened); err != nil {
		return err
	}
	r.NameMatchScore = matchScore
	if matchScore < MinNameMatchScore {
		return save(ctx, r, "VERIFY_BENEFICIARY", StBenRej)
	}
	return save(ctx, r, "VERIFY_BENEFICIARY", StVerified)
}

// ConfirmFunding records that the send-side funds are secured. If the quote has expired
// the remittance moves to EXPIRED (no error, so the state change commits).
func (c *RemitContract) ConfirmFunding(ctx contractapi.TransactionContextInterface,
	id, fundingRef string) error {
	if err := requireMSP(ctx, RemitterMSP); err != nil {
		return err
	}
	r, err := load(ctx, id)
	if err != nil {
		return err
	}
	if err := requireStatus(r, StVerified); err != nil {
		return err
	}
	if fundingRef == "" {
		return fmt.Errorf("fundingRef required")
	}
	now, err := txNow(ctx)
	if err != nil {
		return err
	}
	if now > r.Quote.ExpiresAtUnix {
		return save(ctx, r, "FUNDING_QUOTE_EXPIRED", StExpired)
	}
	vk := velocityKey(r.BeneficiaryHash, now)
	used, err := readVelocity(ctx, vk)
	if err != nil {
		return err
	}
	if used+r.Quote.ReceivePaise > DailyBeneficiaryCapPaise {
		return fmt.Errorf("daily beneficiary cap exceeded")
	}
	if err := writeVelocity(ctx, vk, used+r.Quote.ReceivePaise); err != nil {
		return err
	}
	r.FundingRef = fundingRef
	r.Funded = true
	return save(ctx, r, "CONFIRM_FUNDING", StFunded)
}

// SubmitPayout hands the credit instruction to the payout rail. Idempotent per payoutRef,
// and a payoutRef can never be reused by another remittance (double-payout guard).
func (c *RemitContract) SubmitPayout(ctx contractapi.TransactionContextInterface,
	id, payoutRef string) error {
	if err := requireMSP(ctx, PayoutMSP); err != nil {
		return err
	}
	r, err := load(ctx, id)
	if err != nil {
		return err
	}
	if r.Status == StSubmitted && r.PayoutRef == payoutRef {
		return nil
	}
	if err := requireStatus(r, StFunded); err != nil {
		return err
	}
	if payoutRef == "" {
		return fmt.Errorf("payoutRef required")
	}
	pk := "PAYOUTREF_" + payoutRef
	if b, err := ctx.GetStub().GetState(pk); err != nil {
		return err
	} else if b != nil {
		return fmt.Errorf("payoutRef %s already used", payoutRef)
	}
	if err := ctx.GetStub().PutState(pk, []byte(id)); err != nil {
		return err
	}
	r.PayoutRef = payoutRef
	return save(ctx, r, "SUBMIT_PAYOUT", StSubmitted)
}

// SettlePayout is the final success step, carrying the UPI reference.
func (c *RemitContract) SettlePayout(ctx contractapi.TransactionContextInterface,
	id, upiRef string) error {
	if err := requireMSP(ctx, PayoutMSP); err != nil {
		return err
	}
	r, err := load(ctx, id)
	if err != nil {
		return err
	}
	if r.Status == StSettled && r.UPIRef == upiRef {
		return nil
	}
	if err := requireStatus(r, StSubmitted); err != nil {
		return err
	}
	if upiRef == "" {
		return fmt.Errorf("upiRef required")
	}
	r.UPIRef = upiRef
	return save(ctx, r, "SETTLE_PAYOUT", StSettled)
}

// FailPayout marks the payout as failed so the sender can be refunded.
func (c *RemitContract) FailPayout(ctx contractapi.TransactionContextInterface,
	id, reason string) error {
	if err := requireMSP(ctx, PayoutMSP); err != nil {
		return err
	}
	r, err := load(ctx, id)
	if err != nil {
		return err
	}
	if err := requireStatus(r, StSubmitted); err != nil {
		return err
	}
	r.FailReason = reason
	return save(ctx, r, "FAIL_PAYOUT", StFailed)
}

// Refund returns funds for any non-settled terminal-failure state and releases the velocity budget.
func (c *RemitContract) Refund(ctx contractapi.TransactionContextInterface,
	id, refundRef string) error {
	if err := requireMSP(ctx, RemitterMSP); err != nil {
		return err
	}
	r, err := load(ctx, id)
	if err != nil {
		return err
	}
	if err := requireStatus(r, StFailed, StExpired, StBlocked, StBenRej); err != nil {
		return err
	}
	if refundRef == "" {
		return fmt.Errorf("refundRef required")
	}
	if r.Funded {
		now, err := txNow(ctx)
		if err != nil {
			return err
		}
		// Note: released against the refund-day bucket; acceptable for the prototype.
		vk := velocityKey(r.BeneficiaryHash, now)
		used, err := readVelocity(ctx, vk)
		if err != nil {
			return err
		}
		if err := writeVelocity(ctx, vk, used-r.Quote.ReceivePaise); err != nil {
			return err
		}
	}
	r.RefundRef = refundRef
	return save(ctx, r, "REFUND", StRefunded)
}

// ---------- queries ----------

func (c *RemitContract) GetRemittance(ctx contractapi.TransactionContextInterface, id string) (*Remittance, error) {
	return load(ctx, id)
}

func (c *RemitContract) ListRemittances(ctx contractapi.TransactionContextInterface) ([]*Remittance, error) {
	it, err := ctx.GetStub().GetStateByRange("REM_", "REM`") // '`' sorts right after '_'
	if err != nil {
		return nil, err
	}
	defer it.Close()
	out := []*Remittance{}
	for it.HasNext() {
		kv, err := it.Next()
		if err != nil {
			return nil, err
		}
		var r Remittance
		if err := json.Unmarshal(kv.Value, &r); err != nil {
			return nil, err
		}
		out = append(out, &r)
	}
	return out, nil
}

func (c *RemitContract) GetRemittanceHistory(ctx contractapi.TransactionContextInterface, id string) ([]HistoryEntry, error) {
	it, err := ctx.GetStub().GetHistoryForKey(key(id))
	if err != nil {
		return nil, err
	}
	defer it.Close()
	out := []HistoryEntry{}
	for it.HasNext() {
		m, err := it.Next()
		if err != nil {
			return nil, err
		}
		ts := ""
		if m.Timestamp != nil {
			ts = time.Unix(m.Timestamp.Seconds, int64(m.Timestamp.Nanos)).UTC().Format(time.RFC3339)
		}
		out = append(out, HistoryEntry{TxID: m.TxId, Timestamp: ts, IsDelete: m.IsDelete, Value: string(m.Value)})
	}
	return out, nil
}
