from memoryMgmt.memoryManager import MemoryManager
from models.task import Task


def testAdmissionControlAndRelease():
    manager = MemoryManager(100, schedulerMemoryMb=10)
    first = Task("first", memory=60)
    second = Task("second", memory=40)
    assert manager.admitTask(first)
    assert not manager.admitTask(second)
    assert manager.rejections == ["second"]
    assert manager.availableMemory == 30
    assert manager.releaseTask("first") == 60
    assert manager.availableMemory == 90


def testMigrationIncludesTaskMemory():
    manager = MemoryManager(100)
    task = Task("moving", dataSize=20, memory=30)
    assert manager.getMigrationTime(task, 10) == 5
    assert manager.migrationDataMb == 50


def testLruCache():
    manager = MemoryManager(100, cacheSlots=2, cachePolicy="LRU")
    manager.accessService("video")
    manager.accessService("maps")
    manager.accessService("video")
    manager.accessService("music")
    assert list(manager.cache.keys()) == ["video", "music"]
    assert manager.cacheHits == 1
    assert manager.cacheMisses == 3


def testPredictiveCache():
    manager = MemoryManager(100, cacheSlots=2, cachePolicy="PREDICTIVE")
    manager.accessService("video")
    manager.accessService("maps")
    manager.accessService("video")
    manager.accessService("music")
    assert "video" in manager.cache
    assert "music" in manager.cache
    assert "maps" not in manager.cache


def testSchedulerMemoryReservation():
    manager = MemoryManager(100, schedulerMemoryMb=20)
    assert manager.availableMemory == 80
    assert manager.usedMemory == 20


def runTests():
    testAdmissionControlAndRelease()
    testMigrationIncludesTaskMemory()
    testLruCache()
    testPredictiveCache()
    testSchedulerMemoryReservation()
    print("All standalone Requirement 7 tests passed")


if __name__ == "__main__":
    runTests()
