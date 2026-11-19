from models.device import Device
from models.server import Server
from models.task import Task
from scheduling.offloadStrategy import DRLInspiredHeuristic, ListSchedulingHeuristic, StaticRule
from scheduling.scheduler import Scheduler
from experiments.greenPolicyExperiment import createWorkload, runRequirement6Experiment, runWorkload, tuneAdaptivePolicy
from scheduling.adaptiveGreenPolicy import AdaptiveGreenPolicy
from collections import OrderedDict, deque
from memoryMgmt.memoryManager import MemoryManager
from scheduling.offloadStrategy import StaticRule
from ioMgmt.networkInterface import NetworkInterface
from experiments.scenarioRunner import getScenarios, runAllScenarios

def testPriorityOrder():
    device = Device('LocalDevice', 1.0)
    device.addTask(Task('T1', 10, 3))
    device.addTask(Task('T2', 10, 1))
    device.addTask(Task('T3', 10, 1))
    orderedTasks = [task.id for task in device.getQueueTasks()]
    assert orderedTasks == ['T2', 'T3', 'T1']

def testStaticRule():
    device = Device('LocalDevice', 1.0)
    edge = Server('EdgeServer', 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], StaticRule(50))
    smallTask = Task('Small', 20, 1)
    largeTask = Task('Large', 80, 1)
    assert scheduler.submitTask(smallTask) is device
    assert scheduler.submitTask(largeTask) is edge

def testHeuristic():
    device = Device('LocalDevice', 1.0)
    edge = Server('EdgeServer', 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], DRLInspiredHeuristic())
    largeTask = Task('Large', 80, 1)
    assert scheduler.submitTask(largeTask) is edge

def testMigration():
    device = Device('LocalDevice', 1.0)
    edge = Server('EdgeServer', 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], StaticRule(100))
    task = Task('MoveMe', 80, 1)
    assert scheduler.submitTask(task) is device
    scheduler.strategy = StaticRule(50)
    assert scheduler.submitTask(task) is edge
    assert not device.queue.hasTask('MoveMe')
    assert edge.queue.hasTask('MoveMe')

def testListSchedulingChoosesEarliestFinish():
    device = Device('LocalDevice', 1.0, energyCapacity=500.0)
    edge = Server('EdgeServer', 3.0, wirelessDelay=5.0)
    cloud = Server('CloudServer', 5.0, wirelessDelay=5.0, wiredDelay=10.0)
    scheduler = Scheduler(device, [edge, cloud], ListSchedulingHeuristic())
    localTask = Task('LocalTask', 5, 1)
    edgeTask = Task('EdgeTask', 20, 1, memory=0)
    cloudTask = Task('CloudTask', 100, 1, memory=0)
    assert scheduler.submitTask(localTask) is device
    assert scheduler.submitTask(edgeTask) is edge
    assert scheduler.submitTask(cloudTask) is cloud
    assert device.estimateFinishTime(localTask) == 5.0
    assert round(edge.estimateFinishTime(edgeTask), 2) == 11.67
    assert cloud.estimateFinishTime(cloudTask) == 35.0

def testNetworkDelayIncluded():
    device = Device('LocalDevice', 1.0, energyCapacity=100.0)
    edge = Server('EdgeServer', 3.0, wirelessDelay=5.0)
    task = Task('SmallTask', 5, 1, memory=0)
    assert device.estimateFinishTime(task) == 5.0
    assert round(edge.estimateFinishTime(task), 2) == 6.67

def testEnergyReservationPreventsOversubscription():
    device = Device('LocalDevice', 1.0, energyCapacity=30.0, energyPerWorkUnit=0.5)
    edge = Server('EdgeServer', 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], StaticRule(100))
    firstTask = Task('First', 40, 1)
    secondTask = Task('Second', 30, 1)
    assert scheduler.submitTask(firstTask) is device
    assert device.reservedEnergy == 20.0
    assert scheduler.submitTask(secondTask) is edge
    assert device.reservedEnergy == 20.0

def testEnergyConsumedOnLocalDispatch():
    device = Device('LocalDevice', 1.0, energyCapacity=30.0, energyPerWorkUnit=0.5)
    device.addTask(Task('LocalTask', 20, 1))
    task = device.nextTask()
    assert task.id == 'LocalTask'
    assert device.remainingEnergy == 20.0
    assert device.reservedEnergy == 0.0

def testListSchedulingAvoidsUnaffordableLocalExecution():
    device = Device('LocalDevice', 1.0, energyCapacity=10.0, energyPerWorkUnit=0.5)
    edge = Server('EdgeServer', 3.0, wirelessDelay=5.0)
    scheduler = Scheduler(device, [edge], ListSchedulingHeuristic())
    task = Task('TooExpensiveLocally', 40, 1)
    assert scheduler.submitTask(task) is edge

def testNoExecutionWhenEnergyInsufficientAndNoRemoteServer():
    device = Device('LocalDevice', 1.0, energyCapacity=10.0, energyPerWorkUnit=0.5)
    scheduler = Scheduler(device, [], StaticRule(100))
    task = Task('NoEnergy', 40, 1)
    try:
        scheduler.submitTask(task)
    except ValueError:
        assert task.status == 'new'
    else:
        raise AssertionError('Task should not be admitted without enough energy')

def testUploadTimeUsesDataSizeAndWirelessBandwidth():
    edge = Server('EdgeServer', 3.0, wirelessDelay=2.0, wirelessBandwidth=10.0)
    task = Task('Upload', 20, 1, dataSize=50, memory=0)
    assert edge.getTransferTime(task) == 5.0
    assert edge.getCommunicationDelay(task) == 7.0

def testCloudUploadIncludesWirelessAndWiredTransferTime():
    cloud = Server('CloudServer', 5.0, wirelessDelay=2.0, wiredDelay=4.0, wirelessBandwidth=10.0, wiredBandwidth=100.0)
    task = Task('CloudUpload', 20, 1, dataSize=50, memory=0)
    assert cloud.getTransferTime(task) == 5.5
    assert cloud.getCommunicationDelay(task) == 11.5
    device = Device('LocalDevice', 1.0)
    scheduler = Scheduler(device, [cloud], StaticRule(0))
    assert scheduler.submitTask(task, currentTime=0.0) is cloud
    assert task.status == 'transferring'
    assert task.transferCompletionTime == 11.5
    assert scheduler.dispatchTask('CloudServer', currentTime=11.49) is None
    assert scheduler.dispatchTask('CloudServer', currentTime=11.5) is task

def testRemoteTaskCannotRunBeforeUploadCompletes():
    device = Device('LocalDevice', 1.0)
    edge = Server('EdgeServer', 3.0, wirelessDelay=2.0, wirelessBandwidth=10.0)
    scheduler = Scheduler(device, [edge], StaticRule(0))
    task = Task('DelayedUpload', 20, 1, dataSize=50, memory=0)
    assert scheduler.submitTask(task, currentTime=3.0) is edge
    assert task.status == 'transferring'
    assert task.transferStartTime == 3.0
    assert task.transferCompletionTime == 10.0
    assert scheduler.dispatchTask('EdgeServer', currentTime=9.99) is None
    assert task.status == 'transferring'
    assert edge.queue.hasTask(task.id)
    assert scheduler.dispatchTask('EdgeServer', currentTime=10.0) is task
    assert task.status == 'running'

def testRemoteDispatchRespectsPriorityAmongTransferredTasks():
    device = Device('LocalDevice', 1.0)
    edge = Server('EdgeServer', 3.0, wirelessDelay=0.0, wirelessBandwidth=10.0)
    scheduler = Scheduler(device, [edge], StaticRule(0))
    slowUpload = Task('HighPrioritySlowUpload', 10, 1, dataSize=50, memory=0)
    fastUpload = Task('LowPriorityFastUpload', 10, 2, dataSize=10, memory=0)
    scheduler.submitTask(slowUpload, currentTime=0.0)
    scheduler.submitTask(fastUpload, currentTime=0.0)
    assert scheduler.dispatchTask('EdgeServer', currentTime=1.0) is None
    assert scheduler.dispatchTask('EdgeServer', currentTime=5.0) is slowUpload
    assert scheduler.dispatchTask('EdgeServer', currentTime=6.0) is fastUpload

def testLocalTasksDoNotRequireUpload():
    device = Device('LocalDevice', 1.0, energyCapacity=100.0)
    task = Task('LocalDataTask', 10, 1, dataSize=500)
    device.addTask(task, currentTime=4.0)
    assert task.transferTime == 0.0
    assert task.communicationDelay == 0.0
    assert task.transferCompletionTime == 4.0
    assert device.nextTask(currentTime=4.0) is task

def testBandwidthMustBePositive():
    try:
        Server('InvalidServer', 2.0, wirelessBandwidth=0.0)
    except ValueError:
        pass
    else:
        raise AssertionError('Zero network bandwidth should be rejected')

def testStateContainsRequiredInputs():
    device = Device('Device', energyCapacity=100.0)
    edge = Server('Edge', 3.0, wirelessBandwidth=10.0)
    policy = AdaptiveGreenPolicy(referenceBandwidth=10.0)
    state = policy.buildState(Task('StateTask', 25, 1, dataSize=5), device, [edge])
    assert set(('remainingBattery', 'localQueueLength', 'wirelessSpeed', 'taskSize')).issubset(state)
    assert state['remainingBattery'] == 1.0
    assert state['localQueueLength'] == 0
    assert state['wirelessSpeed'] == 10.0
    assert state['taskSize'] == 25

def testWeightsAdaptToBatteryAndNetwork():
    policy = AdaptiveGreenPolicy(referenceBandwidth=10.0)
    fullBattery = {'remainingBattery': 1.0, 'wirelessSpeed': 10.0}
    lowBattery = {'remainingBattery': 0.2, 'wirelessSpeed': 10.0}
    slowNetwork = {'remainingBattery': 1.0, 'wirelessSpeed': 2.0}
    fullTime, fullEnergy = policy.getAdaptiveWeights(fullBattery)
    lowTime, lowEnergy = policy.getAdaptiveWeights(lowBattery)
    slowTime, slowEnergy = policy.getAdaptiveWeights(slowNetwork)
    assert lowEnergy > fullEnergy
    assert slowEnergy > fullEnergy
    assert slowTime != fullTime
    assert slowEnergy != fullEnergy
    assert abs(fullTime + fullEnergy - 1.0) < 1e-09

def testPolicySelectsAnExecutionPointAndRecordsOverhead():
    device = Device('Device', energyCapacity=100.0)
    edge = Server('Edge', 3.0, wirelessBandwidth=10.0)
    policy = AdaptiveGreenPolicy()
    selected = policy.chooseServer(Task('ChooseTask', 40, 1, dataSize=8), device, [edge])
    summary = policy.getOverheadSummary()
    assert selected in (device, edge)
    assert summary['decisionCount'] == 1
    assert summary['averageDecisionTimeNs'] >= 0
    assert summary['policyMemoryBytes'] > 0
    assert policy.lastState['taskSize'] == 40

def testTrainingAndTestingWorkloadsAreDifferent():
    training = createWorkload(41, 12, 'training')
    testing = createWorkload(97, 12, 'testing')
    trainingIds = {task['id'] for task in training}
    testingIds = {task['id'] for task in testing}
    assert not trainingIds.intersection(testingIds)
    assert training != testing

def testTuningUsesTrainingWorkload():
    training = createWorkload(41, 8, 'training')
    tuning = tuneAdaptivePolicy(training, randomSeed=41)
    assert len(tuning['trials']) == 24
    assert tuning['settings'] is not None
    assert tuning['objective'] >= 0

def testAdaptiveWorkloadRunCompletesAndReportsOverhead():
    workload = createWorkload(97, 12, 'testing')
    result = runWorkload(workload, 'adaptive', {'baseTimeWeight': 0.6, 'baseEnergyWeight': 0.4, 'batterySensitivity': 0.5, 'networkSensitivity': 0.25, 'networkEnergySensitivity': 0.2, 'referenceBandwidth': 12.0}, randomSeed=97)
    assert result['completedTasks'] + result['rejectedTasks'] == len(workload)
    assert result['makespan'] >= 0
    assert result['totalEnergy'] >= 0
    assert result['decisionOverhead']['decisionCount'] == len(workload)
    assert result['decisionOverhead']['policyMemoryBytes'] > 0

def testCompleteRequirement6Comparison():
    report = runRequirement6Experiment(trainingSeed=41, testingSeed=97, taskCount=10)
    assert report['trainingSeed'] != report['testingSeed']
    assert report['tuningTrialCount'] == 24
    assert len(report['seedResults']) == 5
    assert len(report['statistics']['adaptive']['makespan']) == 2
    assert [result['policy'] for result in report['results']] == ['static', 'list', 'adaptive']
    adaptive = report['results'][2]
    assert adaptive['decisionOverhead']['decisionCount'] == 10

def testEachTaskHasMemoryFootprint():
    task = Task('DefaultMemory', 10, 1)
    assert task.memory > 0

def testLocalSchedulerMemoryIsReserved():
    device = Device('Device', memoryCapacity=64.0, schedulerMemoryReserve=16.0)
    Scheduler(device, [], StaticRule(100))
    summary = device.getMemorySummary()
    assert summary['reservedSystemMemoryMb'] == 16.0
    assert summary['capacityMb'] == 64.0

def testMemoryAdmissionRedirectsTaskToRemoteServer():
    device = Device('Device', memoryCapacity=40.0, schedulerMemoryReserve=16.0)
    edge = Server('Edge', 3.0, memoryCapacity=100.0)
    scheduler = Scheduler(device, [edge], StaticRule(100))
    first = Task('LocalOccupant', 10, 1, memory=20.0)
    second = Task('Redirected', 10, 1, memory=20.0)
    assert scheduler.submitTask(first) is device
    assert scheduler.submitTask(second) is edge
    assert device.memoryManager.getSummary()['rejectionCount'] == 1
    assert second.memoryNode == 'Edge'

def testMemoryAdmissionRejectionsAreRecordedOnEveryNode():
    device = Device('Device', memoryCapacity=32.0, schedulerMemoryReserve=16.0)
    edge = Server('Edge', 3.0, memoryCapacity=20.0)
    cloud = Server('Cloud', 5.0, memoryCapacity=20.0)
    scheduler = Scheduler(device, [edge, cloud], StaticRule(100))
    task = Task('TooLarge', 10, 1, memory=30.0)
    assert scheduler.submitTask(task) is None
    assert task.status == 'memoryRejected'
    assert device.memoryManager.getSummary()['rejectionCount'] == 1
    assert edge.memoryManager.getSummary()['rejectionCount'] == 1
    assert cloud.memoryManager.getSummary()['rejectionCount'] == 1

def testMemoryReleasedOnlyAfterCompletion():
    device = Device('Device', memoryCapacity=128.0, schedulerMemoryReserve=16.0)
    scheduler = Scheduler(device, [], StaticRule(100))
    task = Task('Running', 10, 1, memory=24.0)
    assert scheduler.submitTask(task) is device
    assert device.memoryManager.usedTaskMemory == 24.0
    assert scheduler.dispatchTask('Device', 0.0) is task
    assert device.memoryManager.usedTaskMemory == 24.0
    assert scheduler.completeTask('Device', task.id)
    assert device.memoryManager.usedTaskMemory == 0.0

def testMigrationTransfersInputAndMemoryState():
    edge = Server('Edge', 3.0, wirelessDelay=0.0, wirelessBandwidth=10.0)
    task = Task('Migration', 20, 1, dataSize=10.0, memory=20.0)
    assert edge.getTransferTime(task) == 3.0

def testCloudMigrationIncludesWirelessAndWiredStateTransfer():
    cloud = Server('Cloud', 5.0, wirelessDelay=0.0, wiredDelay=1.0, wirelessBandwidth=10.0, wiredBandwidth=100.0)
    task = Task('CloudMigration', 20, 1, dataSize=20.0, memory=10.0)
    assert round(cloud.getTransferTime(task), 2) == 3.3

def testServiceCacheMissAndHitDelay():
    manager = MemoryManager('Edge', 128.0, cacheSlots=2, serviceImageSize=10.0, serviceLoadDelay=4.0)
    assert manager.accessService('analytics', 0.0) == 4.0
    assert manager.accessService('analytics', 1.0) == 0.0
    summary = manager.getSummary()
    assert summary['cacheHits'] == 1
    assert summary['cacheMisses'] == 1
    assert summary['cacheHitRate'] == 0.5
    assert summary['cacheMemoryMb'] == 10.0

def testLruEvictsLeastRecentlyUsedService():
    manager = MemoryManager('Edge', 128.0, cacheSlots=2, cachePolicy='LRU', serviceImageSize=10.0)
    manager.accessService('analytics', 0.0)
    manager.accessService('database', 1.0)
    manager.accessService('analytics', 2.0)
    manager.accessService('vision', 3.0)
    assert list(manager.serviceCache.keys()) == ['analytics', 'vision']
    assert manager.cacheEvictions == 1

def testPredictiveCacheUsesRecentArrivalHistory():
    manager = MemoryManager('Edge', 128.0, cacheSlots=2, cachePolicy='PREDICTIVE', serviceImageSize=10.0)
    manager.serviceCache = OrderedDict((('analytics', 1.0), ('database', 2.0)))
    manager.cacheMemoryUsed = 20.0
    manager.serviceHistory = deque(('analytics', 'analytics', 'analytics', 'database'), maxlen=20)
    manager.accessService('vision', 3.0)
    assert 'analytics' in manager.serviceCache
    assert 'database' not in manager.serviceCache
    assert manager.cachePolicy == 'PREDICTIVE'

def testCacheMissAddsPageLoadStyleDelayToRemoteReadiness():
    device = Device('Device', energyCapacity=1000.0)
    edge = Server('Edge', 3.0, wirelessDelay=0.0, wirelessBandwidth=10.0, memoryCapacity=128.0, cacheSlots=2, serviceImageSize=10.0, serviceLoadDelay=4.0)
    scheduler = Scheduler(device, [edge], StaticRule(0))
    task = Task('CacheMiss', 10, 1, dataSize=10.0, memory=10.0, service='analytics')
    assert scheduler.submitTask(task, 0.0) is edge
    assert task.transferCompletionTime == 6.0
    assert scheduler.dispatchTask('Edge', 5.99) is None
    assert scheduler.dispatchTask('Edge', 6.0) is task

def testMemoryAdmissionRejectsNegativeFootprints():
    manager = MemoryManager('Node', 64.0)
    task = Task('NegativeMemory', 1, 1, memory=-1.0)
    try:
        manager.canAdmit(task)
    except ValueError:
        pass
    else:
        raise AssertionError('Negative memory footprint should be rejected')

def testSerialFcfsUploads():
    device = Device('Device', 1.0, energyCapacity=100.0)
    edge = Server('Edge', 2.0, wirelessBandwidth=10.0)
    network = NetworkInterface(device=device, txPower=0.2)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    first = Task('First', 5, 2, dataSize=20, memory=0)
    second = Task('Second', 5, 1, dataSize=10, memory=0)
    scheduler.submitTask(first, 0.0)
    scheduler.submitTask(second, 0.0)
    assert first.transferStartTime == 0.0
    assert first.transferCompletionTime == 2.0
    assert second.status == 'uploadQueued'
    assert scheduler.dispatchTask('Edge', 1.99) is None
    assert scheduler.dispatchTask('Edge', 2.0) is first
    assert second.transferStartTime == 2.0
    assert second.transferCompletionTime == 3.0
    assert scheduler.dispatchTask('Edge', 3.0) is second

def testPriorityUploadQueue():
    device = Device('Device', 1.0, energyCapacity=100.0)
    edge = Server('Edge', 2.0, wirelessBandwidth=10.0)
    network = NetworkInterface(policy='PRIORITY', device=device)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    first = Task('First', 5, 3, dataSize=10, memory=0)
    second = Task('Second', 5, 1, dataSize=10, memory=0)
    scheduler.submitTask(first, 0.0)
    scheduler.submitTask(second, 0.0)
    assert scheduler.dispatchTask('Edge', 1.0) is first
    assert second.transferStartTime == 1.0
    assert scheduler.dispatchTask('Edge', 2.0) is second

def testTransmissionEnergyIsCharged():
    device = Device('Device', 1.0, energyCapacity=100.0)
    edge = Server('Edge', 2.0, wirelessBandwidth=10.0)
    network = NetworkInterface(device=device, txPower=0.5)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    task = Task('Transmit', 5, 1, dataSize=20, memory=0)
    scheduler.submitTask(task, 0.0)
    assert network.transmissionEnergy == 1.0
    assert device.remainingEnergy == 99.0
    assert network.getEnergySummary()['transmissionEnergy'] == 1.0

def testTransmissionEnergyCannotOverdrawBattery():
    device = Device('Device', 1.0, energyCapacity=1.0)
    edge = Server('Edge', 2.0, wirelessBandwidth=1.0)
    network = NetworkInterface(device=device, txPower=2.0)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    task = Task('TooExpensive', 5, 1, dataSize=1, memory=0)
    scheduler.submitTask(task, 0.0)
    assert task.status == 'energyRejected'
    assert network.energyRejected == ['TooExpensive']
    assert device.remainingEnergy == 1.0

def testRadioSleepsAndWakes():
    device = Device('Device', 1.0, energyCapacity=100.0)
    edge = Server('Edge', 2.0, wirelessBandwidth=10.0)
    network = NetworkInterface(device=device, idleTimeout=2.0, wakeDelay=1.0, wakeEnergy=0.5)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    first = Task('First', 5, 1, dataSize=10, memory=0)
    scheduler.submitTask(first, 0.0)
    scheduler.dispatchTask('Edge', 1.0)
    scheduler.dispatchTask('Edge', 4.0)
    assert network.state == 'sleep'
    second = Task('Second', 5, 1, dataSize=10, memory=0)
    scheduler.submitTask(second, 5.0)
    assert second.transferStartTime == 6.0
    assert second.transferCompletionTime == 7.0
    assert scheduler.dispatchTask('Edge', 5.5) is None
    assert network.state == 'sleep'
    assert scheduler.dispatchTask('Edge', 6.5) is None
    assert scheduler.dispatchTask('Edge', 7.0) is second
    assert network.wakeEnergyConsumed == 0.5
    assert round(network.radioIdleEnergy, 2) == 0.1

def testPredictiveTimeoutUsesRecentArrivals():
    network = NetworkInterface(radioPolicy='predictive', idleTimeout=10.0, predictiveFactor=2.0, minimumTimeout=1.0)
    network.interArrivalTimes = [2.0, 4.0, 6.0]
    assert network.getIdleTimeout() == 8.0

def testBandwidthVariesWithinConfiguredRange():
    device = Device('Device', 1.0, energyCapacity=1000.0)
    edge = Server('Edge', 2.0, wirelessBandwidth=10.0)
    network = NetworkInterface(device=device, bandwidthVariation=0.2, randomSeed=7)
    scheduler = Scheduler(device, [edge], StaticRule(0), networkInterface=network)
    for index in range(4):
        task = Task(f'Task{index}', 1, 1, dataSize=1, memory=0)
        scheduler.submitTask(task, float(index * 2))
        scheduler.dispatchTask('Edge', task.transferCompletionTime)
    values = network.bandwidthHistory
    assert len(set(values)) > 1
    assert all((8.0 <= value <= 12.0 for value in values))

def testFourteenRequiredScenariosExist():
    scenarios = getScenarios()
    assert len(scenarios) == 14
    names = {scenario['name'] for scenario in scenarios}
    assert 'edgeMemoryAmple' in names
    assert 'edgeMemoryConstrained' in names
    assert 'serviceCacheLRU' in names
    assert 'serviceCachePredictive' in names
    assert 'radioFixed' in names
    assert 'radioPredictive' in names
    assert 'bandwidthStable' in names
    assert 'bandwidthFluctuating' in names

def testCacheComparisonChangesOnlyReplacementPolicy():
    scenarios = {scenario['name']: scenario for scenario in getScenarios()}
    lruSettings = dict(scenarios['serviceCacheLRU']['settings'])
    predictiveSettings = dict(scenarios['serviceCachePredictive']['settings'])
    assert lruSettings.pop('cachePolicy') == 'LRU'
    assert predictiveSettings.pop('cachePolicy') == 'PREDICTIVE'
    assert lruSettings == predictiveSettings
    assert scenarios['serviceCacheLRU']['profile'] == 'cache'
    assert scenarios['serviceCachePredictive']['profile'] == 'cache'

def testAllScenariosRunAllPoliciesAcrossFiveSeeds():
    report = runAllScenarios(taskCount=24)
    assert len(report['scenarios']) == 14
    assert len(report['testingSeeds']) >= 5

    requiredRunMetrics = (
        'makespan', 'totalEnergy', 'computationEnergy', 'transmissionEnergy',
        'radioIdleEnergy', 'wakeEnergy', 'completedTasks', 'rejectedTasks',
        'memoryRejectedTasks', 'offloadedTasks', 'localTasks',
        'averageQueueWaitingTime', 'offloadedPercent', 'localPercent',
        'energyEfficiency', 'peakMemoryUtilization', 'averageMemoryUtilization',
        'serviceCacheHitRate', 'migrationDataVolumeMb', 'memoryAdmissionRejections',
        'radioWakeUps', 'objective', 'queueWaitingTimesByNode', 'radioStateTimes',
        'energyBreakdown', 'memory', 'decisionOverhead'
    )
    requiredSummaryMetrics = (
        'makespan', 'totalEnergy', 'completedTasks', 'rejectedTasks',
        'memoryRejectedTasks', 'peakMemoryUtilization', 'averageMemoryUtilization',
        'serviceCacheHitRate', 'migrationDataVolumeMb', 'memoryAdmissionRejections'
    )
    extendedSummaryMetrics = (
        'computationEnergy', 'transmissionEnergy', 'radioIdleEnergy', 'wakeEnergy',
        'offloadedTasks', 'localTasks', 'averageQueueWaitingTime', 'offloadedPercent',
        'localPercent', 'energyEfficiency', 'radioWakeUps', 'objective'
    )

    for scenario in report['scenarios']:
        assert len(scenario['seedResults']) >= 5
        for seedRun in scenario['seedResults']:
            assert {result['policy'] for result in seedRun['results']} == {'static', 'list', 'adaptive'}
            for result in seedRun['results']:
                missingMetrics = set(requiredRunMetrics) - set(result)
                assert not missingMetrics, f"Missing per-run metrics for {result['policy']}: {sorted(missingMetrics)}"
                assert {'computation', 'transmission', 'radioIdle', 'radioWake'}.issubset(result['energyBreakdown'])
                assert {'LocalDevice', 'EdgeServer', 'CloudServer'}.issubset(result['queueWaitingTimesByNode'])
                assert {'LocalDevice', 'EdgeServer', 'CloudServer'}.issubset(result['memory'])
                if result['policy'] == 'adaptive':
                    assert 'averageDecisionTimeNs' in result['decisionOverhead']
                    assert 'policyMemoryBytes' in result['decisionOverhead']

        for policyName in ('static', 'list', 'adaptive'):
            statistics = scenario['statistics'][policyName]
            for metricName in requiredSummaryMetrics:
                assert metricName in statistics, f"Missing required summary metric: {metricName}"
                assert {'mean', 'standardDeviation'}.issubset(statistics[metricName])
            for metricName in extendedSummaryMetrics:
                if metricName in statistics:
                    assert {'mean', 'standardDeviation'}.issubset(statistics[metricName])

            if 'queueWaitingTimesByNode' in statistics:
                assert 'LocalDevice' in statistics['queueWaitingTimesByNode']
            if 'radioStateTimes' in statistics:
                assert 'active' in statistics['radioStateTimes']
            if 'energyBreakdown' in statistics:
                assert 'computation' in statistics['energyBreakdown']
            if 'memoryByNode' in statistics:
                assert 'EdgeServer' in statistics['memoryByNode']
                assert 'mean' in statistics['memoryByNode']['EdgeServer']['averageUtilization']

        adaptiveStatistics = scenario['statistics']['adaptive']
        if 'decisionOverhead' in adaptiveStatistics:
            assert 'averageDecisionTimeNs' in adaptiveStatistics['decisionOverhead']
            assert 'policyMemoryBytes' in adaptiveStatistics['decisionOverhead']

    lru = next((item for item in report['scenarios'] if item['name'] == 'serviceCacheLRU'))
    predictive = next((item for item in report['scenarios'] if item['name'] == 'serviceCachePredictive'))
    assert predictive['statistics']['static']['serviceCacheHitRate']['mean'] != lru['statistics']['static']['serviceCacheHitRate']['mean']

def runAllTests():
    testGroups = {
        "Requirements 1–5": [
            testPriorityOrder,
            testStaticRule,
            testHeuristic,
            testMigration,
            testListSchedulingChoosesEarliestFinish,
            testNetworkDelayIncluded,
            testEnergyReservationPreventsOversubscription,
            testEnergyConsumedOnLocalDispatch,
            testListSchedulingAvoidsUnaffordableLocalExecution,
            testNoExecutionWhenEnergyInsufficientAndNoRemoteServer,
            testUploadTimeUsesDataSizeAndWirelessBandwidth,
            testCloudUploadIncludesWirelessAndWiredTransferTime,
            testRemoteTaskCannotRunBeforeUploadCompletes,
            testRemoteDispatchRespectsPriorityAmongTransferredTasks,
            testLocalTasksDoNotRequireUpload,
            testBandwidthMustBePositive
        ],
        "Requirement 6": [
            testStateContainsRequiredInputs,
            testWeightsAdaptToBatteryAndNetwork,
            testPolicySelectsAnExecutionPointAndRecordsOverhead,
            testTrainingAndTestingWorkloadsAreDifferent,
            testTuningUsesTrainingWorkload,
            testAdaptiveWorkloadRunCompletesAndReportsOverhead,
            testCompleteRequirement6Comparison
        ],
        "Requirement 7": [
            testEachTaskHasMemoryFootprint,
            testLocalSchedulerMemoryIsReserved,
            testMemoryAdmissionRedirectsTaskToRemoteServer,
            testMemoryAdmissionRejectionsAreRecordedOnEveryNode,
            testMemoryReleasedOnlyAfterCompletion,
            testMigrationTransfersInputAndMemoryState,
            testCloudMigrationIncludesWirelessAndWiredStateTransfer,
            testServiceCacheMissAndHitDelay,
            testLruEvictsLeastRecentlyUsedService,
            testPredictiveCacheUsesRecentArrivalHistory,
            testCacheMissAddsPageLoadStyleDelayToRemoteReadiness,
            testMemoryAdmissionRejectsNegativeFootprints
        ],
        "Requirement 8": [
            testSerialFcfsUploads,
            testPriorityUploadQueue,
            testTransmissionEnergyIsCharged,
            testTransmissionEnergyCannotOverdrawBattery,
            testRadioSleepsAndWakes,
            testPredictiveTimeoutUsesRecentArrivals,
            testBandwidthVariesWithinConfiguredRange
        ],
        "Experiment scenarios": [
            testFourteenRequiredScenariosExist,
            testCacheComparisonChangesOnlyReplacementPolicy,
            testAllScenariosRunAllPoliciesAcrossFiveSeeds
        ]
    }
    totalCount = 0
    for groupName, groupTests in testGroups.items():
        print(f"\n{groupName}")
        for testFunction in groupTests:
            testFunction()
            totalCount += 1
        print(f"Passed: {len(groupTests)}")
    print(f"\nAll {totalCount} tests passed.")


if __name__ == "__main__":
    runAllTests()
