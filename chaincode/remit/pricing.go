package main

import (
	"errors"
	"math/big"
)

// Deterministic integer pricing. No floats, no clocks: every peer must compute
// the exact same quote or endorsement fails.
//
// Units:
//   amounts         -> minor units of the send currency (cents, fils, ...)
//   rates           -> INR per 1 major unit of send currency, scaled by 1e6 ("micro")
//   receive amount  -> paise (1/100 INR)
// Because cents and paise are both 1/100 of a major unit,
//   paise = cents * inrPerUnitMicro / 1e6.

const (
	bpsDenom     int64 = 10000
	rateScale    int64 = 1000000
	maxSendMinor int64 = 1000000000 // 10,000,000.00 in major units
	maxBps       int64 = 500
)

// Quote is the fully itemised, immutable price of one remittance.
type Quote struct {
	SendCurrency       string `json:"sendCurrency"`
	SendAmountMinor    int64  `json:"sendAmountMinor"`
	MidRateMicro       int64  `json:"midRateMicro"`
	SpreadBps          int64  `json:"spreadBps"`
	FeeFlatMinor       int64  `json:"feeFlatMinor"`
	FeeBps             int64  `json:"feeBps"`
	FeeTotalMinor      int64  `json:"feeTotalMinor"`
	EffectiveRateMicro int64  `json:"effectiveRateMicro"`
	ReceivePaise       int64  `json:"receivePaise"`
	CostBps            int64  `json:"costBps"` // all-in cost vs mid-market, in basis points
	ExpiresAtUnix      int64  `json:"expiresAtUnix"`
}

// mulDiv computes (a * b) / c using big.Int to avoid int64 overflow.
func mulDiv(a, b, c int64) int64 {
	ab := new(big.Int).Mul(big.NewInt(a), big.NewInt(b))
	return new(big.Int).Div(ab, big.NewInt(c)).Int64()
}

// ComputeQuote prices a remittance. expiresAt is supplied by the caller
// (derived from the transaction timestamp, never time.Now()).
func ComputeQuote(ccy string, sendMinor, midMicro, spreadBps, feeFlat, feeBps, expiresAt int64) (*Quote, error) {
	switch {
	case ccy == "":
		return nil, errors.New("send currency required")
	case sendMinor <= 0 || sendMinor > maxSendMinor:
		return nil, errors.New("send amount out of range")
	case midMicro <= 0:
		return nil, errors.New("mid rate must be positive")
	case spreadBps < 0 || spreadBps > maxBps || feeBps < 0 || feeBps > maxBps:
		return nil, errors.New("spread/fee bps out of range")
	case feeFlat < 0:
		return nil, errors.New("flat fee must be >= 0")
	}
	fee := feeFlat + sendMinor*feeBps/bpsDenom
	if fee >= sendMinor {
		return nil, errors.New("fee exceeds amount")
	}
	eff := midMicro * (bpsDenom - spreadBps) / bpsDenom
	net := sendMinor - fee
	receive := mulDiv(net, eff, rateScale)
	midReceive := mulDiv(sendMinor, midMicro, rateScale)
	if midReceive <= 0 || receive <= 0 {
		return nil, errors.New("amount too small")
	}
	cost := (midReceive - receive) * bpsDenom / midReceive
	return &Quote{
		SendCurrency: ccy, SendAmountMinor: sendMinor, MidRateMicro: midMicro,
		SpreadBps: spreadBps, FeeFlatMinor: feeFlat, FeeBps: feeBps, FeeTotalMinor: fee,
		EffectiveRateMicro: eff, ReceivePaise: receive, CostBps: cost, ExpiresAtUnix: expiresAt,
	}, nil
}
