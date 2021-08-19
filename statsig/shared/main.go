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
		return
	}

	statsig.WrapperSDK(strCpy(sdkKey), &opt, strCpy(name), strCpy(version))
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
		return
	}
	statsig.LogEvent(evt)
}

//export CheckGate
func CheckGate(u string, gate string) bool {
	user := types.StatsigUser{}
	err := json.Unmarshal([]byte(u), &user)
	if err != nil {
		fmt.Print(err)
		return false
	}
	return statsig.CheckGate(user, strCpy(gate))
}

//export GetConfig
func GetConfig(u string, config string) *C.char {
	user := types.StatsigUser{}
	err := json.Unmarshal([]byte(u), &user)
	if err != nil {
		fmt.Print(err)
		return C.CString(string("{}"))
	}
	dc := statsig.GetConfig(user, strCpy(config))
	jConfig, err := json.Marshal(dc)
	if err != nil {
		fmt.Print(err)
		return C.CString(string("{}"))
	}
	return C.CString(string(jConfig))
}

func main() {}

// strings that are passed to us will be deallocated
// make sure we create a copy of them so they dont get corrupted!
func strCpy(in string) string {
	return (in + " ")[:len(in)]
}
