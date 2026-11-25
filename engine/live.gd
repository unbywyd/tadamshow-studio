extends RefCounted
## LIVE CONTROL of a scene (docs/framework-tz.md 7.3): an app or a game drives the scene as it plays, and hears
## what happens in it. stage.gd with --live=<port> (and --live-host=0.0.0.0 to be reached from another device)
## listens for WebSocket connections; every message is one JSON object:
##   a script line, as in scene.json, without a time:   {"who": "loaf", "do": "wave"}   {"who": "loaf", "go": 0.7}
##       (any command of stage.gd; "id": anything - it comes back in the answer)  ->  {"ok": true, "id": ...}
##       or {"error": "...", "id": ...} when it cannot be done (no such hero, action, point...)
##   {"ask": "state"}    -> {"state": {"t": seconds, "heroes": {id: {"x", "depth", "view", "busy": [actions],
##                           "holds": item or "", "plays": instrument or "", "talking": bool}}}}
##   {"ask": "catalog"}  -> {"catalog": {"actions": [...], "heroes": [...], "items": [...], "points": [...]}}
##   {"tap": [x, y]}     a touch at that point of the picture (px), as if tapped on the screen
##   {"ask": "quit"}     -> the player closes
## And by itself, to everyone connected, as it happens:
##   {"event": "done", "what": "wave", "who": "loaf", "t": 3.2}    an action, a walk ("go"), a turn, a line said
##       ("say"), an instrument put down ("play") is over - the same events the script's "after" waits for
##   {"event": "touch", "who": "loaf", "t": 3.4}                   a hero was touched (a tap or a click on it)

var server := TCPServer.new()
var peers: Array = []
var stage: Node
var _sent: Dictionary = {}


func setup(on: Node, port: int, host: String) -> bool:
	stage = on
	var err := server.listen(port, host)
	if err != OK:
		push_error("live: cannot listen on %s:%d (%s)" % [host, port, error_string(err)])
		return false
	print("STAGE LIVE ws://%s:%d" % [host if host != "*" else "0.0.0.0", port])
	return true


func step() -> void:
	while server.is_connection_available():
		var ws := WebSocketPeer.new()
		ws.accept_stream(server.take_connection())
		peers.append(ws)
	var keep: Array = []
	for ws: WebSocketPeer in peers:
		ws.poll()
		var st := ws.get_ready_state()
		if st == WebSocketPeer.STATE_CLOSED:
			continue
		keep.append(ws)
		if st != WebSocketPeer.STATE_OPEN:
			continue
		while ws.get_available_packet_count() > 0:
			var text := ws.get_packet().get_string_from_utf8()
			var reply: Dictionary = _handle(text)
			if not reply.is_empty():
				ws.send_text(JSON.stringify(reply))
	peers = keep
	# what happened since the last step
	for e: Array in stage._events:
		var key := "%d|%s|%s" % [int(e[0]), str(e[1]), str(e[2])]
		if int(e[0]) <= stage.step_no and not _sent.has(key):
			_sent[key] = true
			tell({"event": "done", "what": str(e[2]), "who": str(e[1]), "t": snappedf(int(e[0]) / 60.0, 0.01)})


func tell(msg: Dictionary) -> void:
	var text := JSON.stringify(msg)
	for ws: WebSocketPeer in peers:
		if ws.get_ready_state() == WebSocketPeer.STATE_OPEN:
			ws.send_text(text)


func _handle(text: String) -> Dictionary:
	var d: Variant = JSON.parse_string(text)
	if not (d is Dictionary):
		return {"error": "not a JSON object"}
	var msg: Dictionary = d
	var id: Variant = msg.get("id", null)
	msg.erase("id")
	var ask: String = str(msg.get("ask", ""))
	if ask == "state":
		return {"state": _state(), "id": id}
	if ask == "catalog":
		return {"catalog": {"actions": stage.actions().keys(), "heroes": stage.actors.keys(),
				"items": stage.items.items.keys(), "points": stage.points.keys()}, "id": id}
	if msg.has("tap"):                       # a touch at a point of the picture, from outside
		var tp: Array = msg["tap"]
		touch(Vector2(float(tp[0]), float(tp[1])))
		return {"ok": true, "id": id}
	if ask == "quit":
		stage.get_tree().quit()
		return {"ok": true, "id": id}
	var why := _wrong(msg)
	if why != "":
		return {"error": why, "id": id}
	stage._command(msg)
	return {"ok": true, "id": id}


## What would make a command impossible (the same checks as tools/check_scene.py, the ones that need no file).
func _wrong(msg: Dictionary) -> String:
	var who: String = str(msg.get("who", ""))
	if who != "" and who != "all" and not stage.actors.has(who):
		return "no hero '%s'" % who
	var act: Variant = msg.get("do", null)
	if act is String and not stage.actions().has(act) and not (act as String).begins_with("stamp_"):
		return "no action '%s'" % act
	var go: Variant = msg.get("go", null)
	if go is String and not stage.points.has(go) and not stage.actors.has(go) and not (go in ["out_left", "out_right"]):
		return "no point or hero '%s' to go to" % go
	if msg.has("take") and not stage.items.items.has(str(msg["take"])):
		return "no item '%s'" % str(msg["take"])
	if msg.has("with") and not stage.actors.has(str(msg["with"])):
		return "no hero '%s' to do it with" % str(msg["with"])
	return ""


func _state() -> Dictionary:
	var heroes := {}
	for id: String in stage.actors:
		var a: Variant = stage.actors[id]
		var busy: Array = []
		for r: Variant in a.motion.runs:
			if not r.done and not busy.has(r.id):
				busy.append(r.id)
		var talking := false
		for tk: Array in stage._talk:
			if tk[0] == id and stage.step_no >= int(tk[1]) and stage.step_no < int(tk[2]):
				talking = true
		var held: String = stage.items.held_by(a.motion)
		heroes[id] = {"x": snappedf(stage.space.vx + (a.puppet.body_position().x - stage.space.vx) * stage.space.scale_at(a.z), 0.1) / stage.world.x,
				"depth": snappedf(a.z / maxf(stage.space.depth, 1.0), 0.01), "view": a.view, "busy": busy,
				"holds": held, "plays": a.instruments[0] if not a.instruments.is_empty() else "", "talking": talking,
				"walking": not a.going.is_empty()}
	return {"t": snappedf(stage.step_no / 60.0, 0.01), "heroes": heroes}


## A tap or a click at `screen` (picture px): the hero under it, nearest first.
func touch(screen: Vector2) -> void:
	var best := ""
	var best_z := INF
	for id: String in stage.actors:
		var a: Variant = stage.actors[id]
		if a.out != 0.0:
			continue
		var to_layer: Transform2D = (a.layer as CanvasLayer).transform.affine_inverse()
		var p: Vector2 = to_layer * screen
		for part: String in a.puppet.parts:
			if a.motion._world_box(part).has_point(p) and a.z < best_z:
				best = id
				best_z = a.z
	if best != "":
		tell({"event": "touch", "who": best, "t": snappedf(stage.step_no / 60.0, 0.01)})
