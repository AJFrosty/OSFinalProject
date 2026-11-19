from experiments.scenarioRunner import getScenarios, runAllScenarios


def testFourteenRequiredScenariosExist():
    scenarios = getScenarios()
    assert len(scenarios) == 14
    names = {scenario["name"] for scenario in scenarios}
    assert "edgeMemoryAmple" in names
    assert "edgeMemoryConstrained" in names
    assert "serviceCacheLRU" in names
    assert "serviceCachePredictive" in names
    assert "radioFixed" in names
    assert "radioPredictive" in names
    assert "bandwidthStable" in names
    assert "bandwidthFluctuating" in names


def testCacheComparisonChangesOnlyReplacementPolicy():
    scenarios = {scenario["name"]: scenario for scenario in getScenarios()}
    lruSettings = dict(scenarios["serviceCacheLRU"]["settings"])
    predictiveSettings = dict(scenarios["serviceCachePredictive"]["settings"])
    assert lruSettings.pop("cachePolicy") == "LRU"
    assert predictiveSettings.pop("cachePolicy") == "PREDICTIVE"
    assert lruSettings == predictiveSettings
    assert scenarios["serviceCacheLRU"]["profile"] == "cache"
    assert scenarios["serviceCachePredictive"]["profile"] == "cache"


def testAllScenariosRunAllPoliciesAcrossFiveSeeds():
    report = runAllScenarios(taskCount=24)
    assert len(report["scenarios"]) == 14
    assert len(report["testingSeeds"]) >= 5
    for scenario in report["scenarios"]:
        assert len(scenario["seedResults"]) >= 5
        for seedRun in scenario["seedResults"]:
            assert {result["policy"] for result in seedRun["results"]} == {
                "static", "list", "adaptive"
            }
    lru = next(item for item in report["scenarios"] if item["name"] == "serviceCacheLRU")
    predictive = next(item for item in report["scenarios"] if item["name"] == "serviceCachePredictive")
    assert (
        predictive["statistics"]["static"]["serviceCacheHitRate"]["mean"]
        != lru["statistics"]["static"]["serviceCacheHitRate"]["mean"]
    )


testFourteenRequiredScenariosExist()
testCacheComparisonChangesOnlyReplacementPolicy()
testAllScenariosRunAllPoliciesAcrossFiveSeeds()
print("All scenario runner checks passed")
