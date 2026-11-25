extends Node
## The web build's door: a browser has no disk and no command line, so this scene
##  1. reads ?recipe=<url> from the page address: a JSON
##       { "files": [{ "url", "path" }],                       every file the film needs → user://…
##         "write": [{ "path", "text" }],                      small files given in the recipe itself
##         "args": ["--scene=…", "--seconds=…"],               ONE scene (played as it is), or
##         "shots": [{ "scene": "user://film/sh1", "seconds": 6.01, "frames": 180 }] }   a FILM: shot after shot
##  2. downloads every file into user:// (the browser's own storage) at its path, LANES at a time,
##  3. starts res://stage.tscn with the arguments (stage.gd reads them from Stage.boot_args).
## ?rec=1 with "shots": the film is RENDERED, not played: the page runs the engine with --fixed-fps, so every drawn
## frame is exactly one step of the film however slow the device is, and each frame is handed to the page
## (window.tadamFrame(n, shot, frameInShot)); window.tadamDone(n) ends it. Nothing has to be seen or heard meanwhile.
## The page sees how far the loading got: window.tadamBoot = { state, done, total, error }.

const Stage := preload("res://stage.gd")

## Files come down on LANES requests at once (one after another, ~100 files took most of a minute), in big chunks:
## HTTPRequest hands over one chunk per frame, and at the default 64 KB a 3 MB picture took 45 frames.
const LANES := 6
const CHUNK := 4 << 20

var _files: Array = []
var _args: PackedStringArray = []
var _shots: Array = []
var _i := 0           # files done
var _asked := 0       # files asked for
var _failed := false
var _handed := false  # the page handed the recipe over: it is a page that also says when it is ready (tadamReady)
var _http: HTTPRequest


func _ready() -> void:
	_say("recipe", 0, 0)
	_http = HTTPRequest.new()
	# the browser has already unpacked a gzip answer; unpacking it again fails ("HTTP 200" and no body)
	_http.accept_gzip = false
	add_child(_http)
	_http.request_completed.connect(_on_recipe)
	# the page that started the engine may hand the recipe over itself (it has just asked for it)
	if OS.has_feature("web"):
		var given := str(JavaScriptBridge.eval("window.tadamRecipe ? JSON.stringify(window.tadamRecipe) : ''", true))
		if not given.is_empty():
			_handed = true
			_on_recipe.call_deferred(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), given.to_utf8_buffer())
			return
	var url := _param("recipe")
	if url.is_empty():
		_fail("no ?recipe= in the page address")
		return
	if _http.request(_abs(url)) != OK:
		_fail("cannot ask for the recipe")


func _param(name: String) -> String:
	if not OS.has_feature("web"):
		for a in OS.get_cmdline_user_args():
			if a.begins_with("--%s=" % name):
				return a.trim_prefix("--%s=" % name)
		return ""
	var v: Variant = JavaScriptBridge.eval("new URLSearchParams(location.search).get('%s') || ''" % name, true)
	return str(v)


## "/lab/x.png" → "https://site/lab/x.png": a recipe may name its files from the site's root.
func _abs(url: String) -> String:
	if url.begins_with("/") and OS.has_feature("web"):
		return str(JavaScriptBridge.eval("location.origin", true)) + url
	return url


func _on_recipe(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	_http.request_completed.disconnect(_on_recipe)
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		_fail("recipe: HTTP %d" % code)
		return
	var r: Variant = JSON.parse_string(body.get_string_from_utf8())
	if not (r is Dictionary):
		_fail("recipe: not JSON")
		return
	_files = r.get("files", [])
	_shots = r.get("shots", [])
	# small files handed over in the recipe itself (every shot's scene.json for this cast)
	for w in r.get("write", []):
		var path := str(w["path"])
		DirAccess.make_dir_recursive_absolute(path.get_base_dir())
		var f := FileAccess.open(path, FileAccess.WRITE)
		if f == null:
			_fail("cannot write %s" % path)
			return
		f.store_string(str(w["text"]))
		f.close()
	for a in r.get("args", []):
		_args.append(str(a))
	if _files.is_empty():
		_begin()
		return
	_say("files", 0, _files.size())
	for k in mini(LANES, _files.size()):
		var h := HTTPRequest.new()
		h.accept_gzip = false
		h.download_chunk_size = CHUNK
		add_child(h)
		h.request_completed.connect(_on_file.bind(h))
		_ask(h)


## The next file nobody has asked for yet, on this lane.
func _ask(h: HTTPRequest) -> void:
	if _failed or _asked >= _files.size():
		return
	var k := _asked
	_asked += 1
	h.set_meta("file", k)
	var f: Dictionary = _files[k]
	DirAccess.make_dir_recursive_absolute(str(f["path"]).get_base_dir())
	if h.request(_abs(str(f["url"]))) != OK:
		_fail("cannot ask for %s" % f["url"])


func _on_file(result: int, code: int, _h: PackedStringArray, body: PackedByteArray, h: HTTPRequest) -> void:
	if _failed:
		return
	var file: Dictionary = _files[int(h.get_meta("file"))]
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		_fail("file %s: HTTP %d" % [file["url"], code])
		return
	# written by hand: HTTPRequest.download_file leaves the file empty in the web build
	var f := FileAccess.open(str(file["path"]), FileAccess.WRITE)
	if f == null:
		_fail("cannot write %s" % file["path"])
		return
	f.store_buffer(body)
	f.close()
	_i += 1
	_say("files", _i, _files.size())
	if _i >= _files.size():
		_begin()
	else:
		_ask(h)


## Every file is in place: the film (or the one scene) begins. A recording waits for the page to be ready to take
## frames (window.tadamReady: its encoder and the film's sound are set up meanwhile, while the files came down).
func _begin() -> void:
	if _handed and _param("rec") != "":
		while not bool(JavaScriptBridge.eval("!!window.tadamReady", true)):
			await get_tree().process_frame
	_say("start", _i, _files.size())
	# ?res=720: draw the film at 720x1280 and stretch it to the screen (a phone's screen has ~3x more pixels)
	if _param("res") != "":
		get_tree().root.content_scale_mode = Window.CONTENT_SCALE_MODE_VIEWPORT
		get_tree().root.content_scale_size = Vector2i(int(_param("res")), int(int(_param("res")) * 16 / 9))
	if not _shots.is_empty():
		var film := Film.new()
		film.shots = _shots
		film.record = _param("rec") != ""
		film.boot_id = get_instance_id()
		get_tree().root.add_child.call_deferred(film)
		return
	Stage.boot_args = _args
	get_tree().change_scene_to_file("res://stage.tscn")


func _say(state: String, done: int, total: int, error := "") -> void:
	print("BOOT %s %d/%d %s" % [state, done, total, error])
	if OS.has_feature("web"):
		JavaScriptBridge.eval("window.tadamBoot = %s" % JSON.stringify({ "state": state, "done": done, "total": total, "error": error }), true)


func _fail(why: String) -> void:
	_failed = true
	push_error("boot: " + why)
	_say("error", _i, _files.size(), why)


## A FILM: the shots one after another, each a stage of its own. Lives at the root, over the scene changes.
## Every shot gives exactly its "frames" frames. The first frame drawn after a scene change is skipped: the new
## stage has not been processed yet on it (a native recording never has such a frame), so frame k of a shot here is
## frame k of the same shot filmed natively.
class Film extends Node:
	const StageScript := preload("res://stage.gd")
	var shots: Array = []
	var record := false
	var boot_id := 0
	var _k := -1          # the shot being filmed
	var _left := 0        # its frames still to give
	var _in_shot := 0
	var _n := 0           # frames given in all
	var _old := 0         # the scene being left (its instance id)
	var _switching := false
	var _over := false

	func _ready() -> void:
		_old = boot_id
		RenderingServer.frame_post_draw.connect(_drawn)
		_shot()

	func _shot() -> void:
		_k += 1
		if _k >= shots.size():
			_over = true
			_js("window.tadamDone && window.tadamDone(%d)" % _n)
			return
		var s: Dictionary = shots[_k]
		StageScript.boot_args = PackedStringArray(["--scene=%s" % s["scene"], "--seconds=%s" % s["seconds"]])
		_left = int(s["frames"])
		_in_shot = 0
		_switching = true
		get_tree().change_scene_to_file.call_deferred("res://stage.tscn")

	func _drawn() -> void:
		if _over:
			return
		var sc := get_tree().current_scene
		if _switching:
			if sc == null or sc.get_instance_id() == _old or not sc.is_node_ready():
				return
			_switching = false      # the new stage is in: this frame is the unprocessed one, skipped
			_old = sc.get_instance_id()
			return
		if record:
			_js("window.tadamFrame && window.tadamFrame(%d, %d, %d)" % [_n, _k, _in_shot])
		_n += 1
		_in_shot += 1
		_left -= 1
		if _left <= 0:
			_shot()

	func _js(code: String) -> void:
		if OS.has_feature("web"):
			JavaScriptBridge.eval(code, true)
		else:
			print("FILM " + code)
