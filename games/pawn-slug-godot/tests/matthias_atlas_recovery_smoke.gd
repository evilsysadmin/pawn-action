extends SceneTree

const ArtProbe := preload("res://tests/matthias_atlas_recovery_probe.gd")
const MatthiasArt := preload("res://scripts/matthias_art.gd")
var _failures: Array[String] = []
var _completed := false

func _initialize() -> void:
    call_deferred("_run")
    call_deferred("_watchdog")

func _watchdog() -> void:
    # SceneTree scripts can keep running after a runtime assertion/error.
    # Bound failures so CI reports them rather than hanging the entire job.
    await create_timer(12.0).timeout
    if not _completed:
        push_error("Matthias atlas recovery smoke timed out (check preceding Godot errors)")
        quit(1)

func _expect(value: bool, note: String) -> void:
    if value:
        return
    _failures.append(note)
    push_error("Atlas recovery smoke: " + note)

func _new_probe():
    var art := ArtProbe.new()
    root.add_child(art)
    return art

func _begin_early_pickup(art) -> void:
    # Real game is already running with visible pistol, while its normal
    # background full-bank warmup is downloading the machinegun.
    art._weapon = "pistol"
    art._rendered_weapon = "pistol"
    art._body_ready = true
    art._body.visible = true
    art._bootstrap_startup_pending = false
    art._bootstrap_full_pending = 1
    art._background_full_inflight_weapon = "machinegun"
    art.set_weapon("machinegun")
    _expect(art.current_weapon() == "machinegun", "pickup equips authored SMG")
    _expect(not art.body_ready(), "unloaded SMG cannot impersonate ready pistol")
    _expect(not art._body.visible, "old pistol body hidden during genuine SMG warmup")
    _expect(art.foreground_requests.is_empty(),
        "one in-flight background SMG bank prevents duplicate foreground download")

func _run() -> void:
    var art = _new_probe()
    await process_frame
    _expect(
        MatthiasArt.ATLAS_DOWNLOAD_TIMEOUT_SECONDS >= 40.0
        and MatthiasArt.ATLAS_DOWNLOAD_TIMEOUT_SECONDS <= 120.0,
        "finite, conservative atlas download timeout replaces infinite default",
    )

    _begin_early_pickup(art)
    # Simulate the existing HTTPRequest RESULT_TIMEOUT reaching the same
    # exhausted-retry callback as any failed background request. The next
    # background bank must progress, while selected SMG receives foreground
    # fallback ownership instead of remaining invisible forever.
    art._background_full_queue.clear()
    art._background_full_queue.append("shotgun")
    art._settle_bootstrap_request("machinegun", "full-v9", false)
    await process_frame
    await process_frame
    _expect(
        art.background_requests.has("shotgun:full-v9"),
        "background queue continues after SMG full-bank exhaustion",
    )
    _expect(
        art.foreground_requests.count("machinegun:full-v9") == 1,
        "selected SMG gets exactly one foreground recovery request",
    )
    _expect(not art._body.visible and not art.body_ready(),
        "no false pistol sprite or playable state while SMG is missing",
    )

    # A successful foreground recovery provides frames for the *selected*
    # weapon, not stale frames from the previous pistol or pending shotgun.
    var image := Image.create(32, 32, false, Image.FORMAT_RGBA8)
    image.fill(Color.WHITE)
    var frames := SpriteFrames.new()
    frames.remove_animation("default")
    frames.add_animation("idle")
    frames.set_animation_loop("idle", true)
    frames.add_frame("idle", ImageTexture.create_from_image(image))
    MatthiasArt._full_frames_by_weapon["machinegun"] = frames
    MatthiasArt._v9_ready_by_weapon["machinegun"] = true
    art._install_or_request_weapon()
    _expect(art.body_ready() and art._body.visible,
        "decoded selected SMG bank restores visible, playable Matthias")
    _expect(art._rendered_weapon == "machinegun",
        "recovery never reinstalls the old pistol silhouette")

    # Foreground pistol overlay is still downloading when a new unready
    # machinegun is picked up. The stale request must be cancelled at once,
    # not after a long network timeout; the selected bank owns the slot.
    var stale = _new_probe()
    await process_frame
    stale._weapon = "pistol"
    stale._rendered_weapon = "pistol"
    stale._body_ready = true
    stale._body.visible = true
    var old_request := HTTPRequest.new()
    stale.add_child(old_request)
    stale._atlas_request = old_request
    stale._atlas_request_weapon = "pistol"
    stale._atlas_request_layout = "run12-v22"
    stale.set_weapon("machinegun")
    _expect(old_request.is_queued_for_deletion(), "stale pistol request cancelled immediately")
    _expect(stale.foreground_requests.count("machinegun:full-v9") == 1,
        "SMG full bank takes over foreground slot immediately")
    _expect(stale._atlas_request_weapon == "machinegun",
        "request ownership follows the selected weapon, not the old pistol")
    _expect(not stale.body_ready() and not stale._body.visible,
        "new weapon remains genuinely hidden until its authored atlas arrives")
    stale.queue_free()

    # Defensive callback path: if an optional request completes after a
    # selection race while its request is already owned, it must resume the
    # uncached selected bank instead of returning with _body_ready=false.
    for optional_layout in ["run12-v22", "locomotion-v10"]:
        var pending = _new_probe()
        await process_frame
        pending._weapon = "machinegun"
        pending._rendered_weapon = ""
        pending._body_ready = false
        pending._body.visible = false
        var optional := HTTPRequest.new()
        pending.add_child(optional)
        pending._atlas_request = optional
        pending._atlas_request_weapon = "pistol"
        pending._atlas_request_layout = optional_layout
        pending._on_atlas_loaded(
            HTTPRequest.RESULT_CANT_CONNECT, 0, PackedStringArray(), PackedByteArray()
        )
        await process_frame
        _expect(pending.foreground_requests.count("machinegun:full-v9") == 1,
            optional_layout + " completion resumes the waiting selected weapon")
        _expect(pending._atlas_request_weapon == "machinegun",
            "optional completion does not reinstall stale pistol bank")
        pending.queue_free()
    await process_frame

    # Do not leak the fake static cache into any other test and do not touch CDN.
    MatthiasArt._full_frames_by_weapon.erase("machinegun")
    MatthiasArt._v9_ready_by_weapon.erase("machinegun")
    art.queue_free()
    await process_frame
    _completed = true
    if not _failures.is_empty():
        print("FAIL Matthias atlas recovery: %d" % _failures.size())
        quit(1)
        return
    print("OK Matthias SMG: early pickup, bounded timeout, foreground recovery, cancelled stale requests, optional callback resume")
    quit(0)
