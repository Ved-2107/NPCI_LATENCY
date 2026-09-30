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

