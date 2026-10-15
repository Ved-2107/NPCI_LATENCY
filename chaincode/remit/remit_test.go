package main

import (
	"encoding/json"
	"testing"
)

func TestPolicyConstants(t *testing.T) {
	if RiskHoldThreshold != 60 {
		t.Errorf("RiskHoldThreshold want 60 got %d", RiskHoldThreshold)
	}
	if RiskBlockThreshold != 85 {
		t.Errorf("RiskBlockThreshold want 85 got %d", RiskBlockThreshold)
	}
	if MinNameMatchScore != 70 {
		t.Errorf("MinNameMatchScore want 70 got %d", MinNameMatchScore)
	}
	if DailyBeneficiaryCapPaise != 500000000 {
		t.Errorf("DailyBeneficiaryCapPaise want 500000000 got %d", DailyBeneficiaryCapPaise)
	}
}

func TestAllowedPurposes(t *testing.T) {
	valid := []string{"FAMILY_MAINTENANCE", "EDUCATION", "MEDICAL", "GIFT", "INVESTMENT", "TRAVEL"}
	for _, p := range valid {
		if !allowedPurposes[p] {
			t.Errorf("purpose %s should be allowed", p)
		}
	}
	invalid := []string{"GAMBLING", "WEAPONS", "CRYPTO_SPECULATION", ""}
	for _, p := range invalid {
		if allowedPurposes[p] {
			t.Errorf("purpose %s should NOT be allowed", p)
		}
	}
}

func TestRemittanceJsonSerialization(t *testing.T) {
	remit := Remittance{
		DocType:         "remittance",
		ID:              "RTEST12345",
		Corridor:        "US-IN",
		SenderHash:      "hash_sender_1",
		BeneficiaryHash: "hash_ben_1",
		Purpose:         "FAMILY_MAINTENANCE",
		Status:          StCreated,
		CreatedAt:       1700000000,
		UpdatedAt:       1700000000,
		Trail: []TrailEntry{
			{
				Step:   "CREATE",
				Status: StCreated,
				Org:    RemitterMSP,
				TxID:   "tx_init_1",
				TS:     1700000000,
			},
		},
	}

	raw, err := json.Marshal(remit)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}

	var parsed Remittance
	if err := json.Unmarshal(raw, &parsed); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	if parsed.ID != "RTEST12345" || parsed.Status != StCreated || len(parsed.Trail) != 1 {
		t.Errorf("parsed struct mismatch: %+v", parsed)
	}
}

func TestStatusConstants(t *testing.T) {
	expectedStatuses := map[string]string{
		"StCreated":   StCreated,
		"StQuoted":    StQuoted,
		"StScreened":  StScreened,
		"StHeld":      StHeld,
		"StBlocked":   StBlocked,
		"StVerified":  StVerified,
		"StBenRej":    StBenRej,
		"StFunded":    StFunded,
		"StExpired":   StExpired,
		"StSubmitted": StSubmitted,
		"StSettled":   StSettled,
		"StFailed":    StFailed,
		"StRefunded":  StRefunded,
	}

	for name, val := range expectedStatuses {
		if val == "" {
			t.Errorf("status constant %s must not be empty", name)
		}
	}
}
