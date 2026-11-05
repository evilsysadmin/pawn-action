extends "res://scripts/matthias_art.gd"

# A deterministic offline probe: it exercises the actual selection and
# background failure recovery paths without loading a remote PNG in CI.
var foreground_requests: Array[String] = []
var background_requests: Array[String] = []

func _ready() -> void:
    _build_nodes()

func _request_atlas(weapon_id: String, _url: String, layout: String) -> void:
    foreground_requests.append("%s:%s" % [weapon_id, layout])
    if _atlas_request == null:
        _atlas_request = HTTPRequest.new()
        _atlas_request_weapon = weapon_id
        _atlas_request_layout = layout
        add_child(_atlas_request)

func _start_bootstrap_request(
    weapon_id: String,
    _url: String,
    layout: String,
    _attempt: int,
) -> void:
    background_requests.append("%s:%s" % [weapon_id, layout])
