package main

import (
	"log"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

func main() {
	cc, err := contractapi.NewChaincode(&RemitContract{})
	if err != nil {
		log.Fatalf("create remit chaincode: %v", err)
	}
	if err := cc.Start(); err != nil {
		log.Fatalf("start remit chaincode: %v", err)
	}
}
