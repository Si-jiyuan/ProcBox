import Foundation
import AppKit
import ApplicationServices
import CoreAudio
import CoreMediaIO

func emit(_ payload: [String: Any]) {
    guard JSONSerialization.isValidJSONObject(payload),
          let data = try? JSONSerialization.data(withJSONObject: payload),
          let line = String(data: data, encoding: .utf8) else { return }
    print(line)
    fflush(stdout)
}

func frontmostPID() -> pid_t? {
    NSWorkspace.shared.frontmostApplication?.processIdentifier
}

func audioProcesses() -> (input: [Int], output: [Int]) {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyProcessObjectList,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var size: UInt32 = 0
    let system = AudioObjectID(kAudioObjectSystemObject)
    guard AudioObjectGetPropertyDataSize(system, &address, 0, nil, &size) == noErr else {
        return ([], [])
    }
    let count = Int(size) / MemoryLayout<AudioObjectID>.size
    guard count > 0 else { return ([], []) }
    var objects = [AudioObjectID](repeating: 0, count: count)
    var dataSize = size
    guard AudioObjectGetPropertyData(system, &address, 0, nil, &dataSize, &objects) == noErr else {
        return ([], [])
    }

    var inputs: [Int] = []
    var outputs: [Int] = []

    for object in objects {
        var pid: pid_t = 0
        var pidAddress = AudioObjectPropertyAddress(
            mSelector: kAudioProcessPropertyPID,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var pidSize = UInt32(MemoryLayout<pid_t>.size)
        guard AudioObjectGetPropertyData(object, &pidAddress, 0, nil, &pidSize, &pid) == noErr else {
            continue
        }

        func isRunning(_ selector: AudioObjectPropertySelector) -> Bool {
            var address = AudioObjectPropertyAddress(
                mSelector: selector,
                mScope: kAudioObjectPropertyScopeGlobal,
                mElement: kAudioObjectPropertyElementMain
            )
            var value: UInt32 = 0
            var valueSize = UInt32(MemoryLayout<UInt32>.size)
            let status = AudioObjectGetPropertyData(object, &address, 0, nil, &valueSize, &value)
            return status == noErr && value != 0
        }

        if isRunning(kAudioProcessPropertyIsRunningInput) {
            inputs.append(Int(pid))
        }
        if isRunning(kAudioProcessPropertyIsRunningOutput) {
            outputs.append(Int(pid))
        }
    }
    return (inputs, outputs)
}

func cameraRunning() -> Bool {
    var address = CMIOObjectPropertyAddress(
        mSelector: CMIOObjectPropertySelector(kCMIOHardwarePropertyDevices),
        mScope: CMIOObjectPropertyScope(kCMIOObjectPropertyScopeGlobal),
        mElement: 0
    )
    var size: UInt32 = 0
    let system = CMIOObjectID(kCMIOObjectSystemObject)
    guard CMIOObjectGetPropertyDataSize(system, &address, 0, nil, &size) == noErr else {
        return false
    }
    let count = Int(size) / MemoryLayout<CMIOObjectID>.size
    guard count > 0 else { return false }
    var devices = [CMIOObjectID](repeating: 0, count: count)
    var used = UInt32(0)
    guard CMIOObjectGetPropertyData(system, &address, 0, nil, size, &used, &devices) == noErr else {
        return false
    }

    let runningSelectors: [CMIOObjectPropertySelector] = [
        CMIOObjectPropertySelector(kCMIODevicePropertyDeviceIsRunningSomewhere),
        CMIOObjectPropertySelector(kCMIODevicePropertyDeviceIsRunning)
    ]
    for device in devices {
        for selector in runningSelectors {
            var runningAddress = CMIOObjectPropertyAddress(
                mSelector: selector,
                mScope: CMIOObjectPropertyScope(kCMIOObjectPropertyScopeGlobal),
                mElement: 0
            )
            var running: UInt32 = 0
            let runningSize = UInt32(MemoryLayout<UInt32>.size)
            var used = UInt32(0)
            let status = CMIOObjectGetPropertyData(
                device,
                &runningAddress,
                0,
                nil,
                runningSize,
                &used,
                &running
            )
            if status == noErr && running != 0 {
                return true
            }
        }
    }
    return false
}

func installKeyboardTap() {
    let mask = CGEventMask(1 << CGEventType.keyDown.rawValue)
    let callback: CGEventTapCallBack = { _, type, event, _ in
        if type == .keyDown, let app = NSWorkspace.shared.frontmostApplication {
            emit(["typing": Int(app.processIdentifier)])
        }
        return Unmanaged.passUnretained(event)
    }

    guard let tap = CGEvent.tapCreate(
        tap: .cgSessionEventTap,
        place: .headInsertEventTap,
        options: .listenOnly,
        eventsOfInterest: mask,
        callback: callback,
        userInfo: nil
    ) else {
        emit(["error": "input_monitoring_permission"])
        return
    }

    let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), source, .commonModes)
    CGEvent.tapEnable(tap: tap, enable: true)
}

installKeyboardTap()

Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
    let audio = audioProcesses()
    emit([
        "audio_in": audio.input,
        "audio_out": audio.output,
        "camera": cameraRunning(),
        "frontmost": Int(frontmostPID() ?? 0)
    ])
}

RunLoop.main.run()
