package main

import "C"

import (
	"encoding/json"
	"fmt"

	statsig "github.com/statsig-io/go-sdk"
	"github.com/statsig-io/go-sdk/types"
)

//export Initialize
func Initialize(sdkKey string, oJson string, name string, version string) {
	opt := types.StatsigOptions{}
	err := json.Unmarshal([]byte(oJson), &opt)
	if err != nil {
		fmt.Print(err)
	}
	statsig.WrapperSDK(sdkKey, &opt, name, version)
}

//export Shutdown
func Shutdown() {
	statsig.Shutdown()
}

//export LogEvent
func LogEvent(eJson string) {
	evt := types.StatsigEvent{}
	err := json.Unmarshal([]byte(eJson), &evt)
	if err != nil {
		fmt.Print(err)
	}
	statsig.LogEvent(evt)
}

//export CheckGate
func CheckGate(u string, gate string) bool {
	user := types.StatsigUser{}
	err := json.Unmarshal([]byte(u), &user)
	if err != nil {
		fmt.Print(err)
	}
	return statsig.CheckGate(user, gate)
}

//export GetConfig
func GetConfig(u string, config string) *C.char {
	user := types.StatsigUser{}
	err := json.Unmarshal([]byte(u), &user)
	if err != nil {
		fmt.Print(err)
	}
	dc := statsig.GetConfig(user, config)
	jConfig, err := json.Marshal(dc)
	if err != nil {
		fmt.Print(err)
	}
	return C.CString(string(jConfig))
}

func main() {}
