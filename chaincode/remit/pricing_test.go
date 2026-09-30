package main

import (
	"encoding/json"
	"os"
	"testing"
)

type vector struct {
	Name   string           `json:"name"`
	Ccy    string           `json:"ccy"`
	Input  map[string]int64 `json:"input"`
	Expect map[string]int64 `json:"expect"`
}

// Shared with hub/tests: Python and Go must price identically.
func TestQuoteVectors(t *testing.T) {
	raw, err := os.ReadFile("../../testvectors/quote_vectors.json")
	if err != nil {
		t.Fatal(err)
	}
	var vs []vector
	if err := json.Unmarshal(raw, &vs); err != nil {
		t.Fatal(err)
	}
	for _, v := range vs {
		q, err := ComputeQuote(v.Ccy, v.Input["sendMinor"], v.Input["midMicro"], v.Input["spreadBps"],
			v.Input["feeFlat"], v.Input["feeBps"], 0)
		if err != nil {
			t.Fatalf("%s: %v", v.Name, err)
		}
		if q.ReceivePaise != v.Expect["receivePaise"] || q.FeeTotalMinor != v.Expect["feeTotalMinor"] ||
			q.CostBps != v.Expect["costBps"] || q.EffectiveRateMicro != v.Expect["effectiveRateMicro"] {
			t.Errorf("%s: got %+v want %+v", v.Name, q, v.Expect)
		}
	}
}

func TestQuoteRejectsBadInput(t *testing.T) {
	if _, err := ComputeQuote("USD", 0, 88000000, 30, 100, 20, 0); err == nil {
		t.Error("zero amount must fail")
	}
	if _, err := ComputeQuote("USD", 50, 88000000, 30, 100, 20, 0); err == nil {
		t.Error("fee >= amount must fail")
	}
}
