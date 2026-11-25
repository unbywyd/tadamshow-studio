extends Node
## THE KIT'S LOCAL PLAYER (`tadam play`, `tadam frames`, `tadam film`): the shots of an episode one after another,
## each a stage of its own (res://stage.tscn), with what the site lays over the picture: the title cards, and the
## lines as SUBTITLES with the speaker's name (nothing is recorded locally). The sound of the whole episode is one
## file mixed beforehand by `tadam` (narration, music, the place), played from the shot the run starts at.
##
## run: godot --path engine res://player.tscn -- --playlist=<file.json> [--font=<ttf>] [--board-preview]
## The playlist (written by tadam, a file of its own for every run, never in this folder):
##   "mode": "play" (a window, in real time) | "snap" (only the frames asked for, as fast as it goes) |
##           "film" (every frame, with --write-movie and --fixed-fps <fps>)
##   "fps": 30                      frames a second of the film (snap: 60, one step a frame)
##   "size": [720, 1280]            the picture (snap and film set the window to it, borderless)
##   "start": 0                     the shot to begin with;  "audio": "<file.wav>", "audio_from": seconds into it
##   "fonts": {"text": ttf, "italic": ttf}
##   "shots": [{ "id", "scene": "<folder with scene.json>", "seconds", "frames",
##               "card": { "image": png, "from", "to", "fade" },
##               "subs": [{ "from", "to", "who": "Корова", "text": "…", "kind": "line" | "narration" }] }]
##   "snaps": [{ "shot": index, "frame": n, "out": "<file.png>" }]      (snap: in order of shot and frame)
## Frames are counted as the site's film counts them (engine/web_boot.gd Film): a shot gives exactly its "frames"
## frames, and its frame 0 is drawn after the stage's first steps, so frame k here is frame k of the site's film.
## Lines printed: "PLAYER shot <id>", "PLAYER snap <file>", "PLAYER done".

const StageScript := preload("res://stage.gd")
const StageScene := preload("res://stage.tscn")
const FxScript := preload("res://fx.gd")

const INK := Color(0.13, 0.12, 0.10, 0.82)
const PAPER := Color(0.99, 0.97, 0.92)
const NAME := Color(0.98, 0.80, 0.42)

var plan: Dictionary = {}
var shots: Array = []
var mode := "play"
var k := -1                  # the shot on the stage now
var stage: Node = null
var _drawn := 0              # frames of this shot drawn (snap, film)
var _snaps: Array = []
var _snap_i := 0
var _over := false
var _end_at := -1.0

var overlay: CanvasLayer
var card: TextureRect
var sub_box: PanelContainer
var sub_name: Label
var sub_text: Label
var _sub_fonts: Dictionary = {}
var audio: AudioStreamPlayer


func _ready() -> void:
	var path := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--playlist="):
			path = a.trim_prefix("--playlist=")
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if path != "" else null
	if not (parsed is Dictionary):
		push_error("player: cannot read the playlist %s" % path)
		get_tree().quit(1)
		return
	plan = parsed
	shots = plan.get("shots", [])
	mode = str(plan.get("mode", "play"))
	_snaps = plan.get("snaps", [])
	if mode != "play":
		var sz: Array = plan.get("size", [720, 1280])
		var w := get_window()
		w.borderless = true          # (a framed window taller than the screen is shrunk by the system)
		w.size = Vector2i(int(sz[0]), int(sz[1]))
	_overlay()
	if mode == "play" and str(plan.get("audio", "")) != "":
		var st: AudioStream = _sound(str(plan["audio"]))
		if st != null:
			audio = AudioStreamPlayer.new()
			audio.stream = st
			add_child(audio)
	RenderingServer.frame_post_draw.connect(_on_drawn)
	if mode == "snap":
		if _snaps.is_empty():
			_finish()
			return
		_shot(int(_snaps[0]["shot"]))
	else:
		_shot(int(plan.get("start", 0)))
		if audio != null:
			audio.play(float(plan.get("audio_from", 0.0)))
		elif mode == "film" and str(plan.get("audio", "")) != "":
			# (filmed: the movie writer records what the engine plays, in step with the frames)
			var st2: AudioStream = _sound(str(plan["audio"]))
			if st2 != null:
				audio = AudioStreamPlayer.new()
				audio.stream = st2
				add_child(audio)
				audio.play(float(plan.get("audio_from", 0.0)))


static func _sound(f: String) -> AudioStream:
	if not FileAccess.file_exists(f):
		return null
	match f.get_extension().to_lower():
		"wav":
			return AudioStreamWAV.load_from_file(f)
		"ogg":
			return AudioStreamOggVorbis.load_from_file(f)
		"mp3":
			return AudioStreamMP3.load_from_file(f)
	return null


## The next shot on the stage: the old one goes, the new one is ready at once (its pictures are read now).
func _shot(i: int) -> void:
	if stage != null:
		remove_child(stage)
		stage.queue_free()
		stage = null
	k = i
	_drawn = 0
	if k < 0 or k >= shots.size():
		_finish()
		return
	var s: Dictionary = shots[k]
	StageScript.boot_args = PackedStringArray(["--scene=%s" % s["scene"], "--seconds=%s" % s["seconds"]])
	stage = StageScene.instantiate()
	add_child(stage)
	move_child(stage, 0)                 # (under the overlay)
	card.visible = false
	card.texture = null
	var cd: Variant = s.get("card", null)
	if cd is Dictionary and FileAccess.file_exists(str(cd.get("image", ""))):
		var im := Image.load_from_file(str(cd["image"]))
		if im != null:
			card.texture = ImageTexture.create_from_image(im)
	print("PLAYER shot %s" % s.get("id", k))


func _finish() -> void:
	if _over:
		return
	_over = true
	print("PLAYER done")
	get_tree().quit()


func _physics_process(_delta: float) -> void:
	if _over or stage == null:
		return
	if mode == "play":
		var steps: int = int(round(float(shots[k]["seconds"]) * 60.0))
		if int(stage.step_no) >= steps:
			if k + 1 < shots.size():
				_shot(k + 1)
			elif _end_at < 0.0:
				_end_at = Time.get_ticks_msec() / 1000.0 + 0.8      # the last picture stays a moment
	if _end_at > 0.0 and Time.get_ticks_msec() / 1000.0 >= _end_at:
		_finish()


func _process(_delta: float) -> void:
	if stage != null and not _over:
		_lay_over(int(stage.step_no) / 60.0)


func _unhandled_input(event: InputEvent) -> void:
	if mode == "play" and event is InputEventKey and event.pressed and event.keycode in [KEY_ESCAPE, KEY_Q]:
		_finish()


## Snap and film count the frames drawn, as the site's film does (engine/web_boot.gd Film).
func _on_drawn() -> void:
	if _over or stage == null or mode == "play":
		return
	if mode == "snap":
		while _snap_i < _snaps.size() and int(_snaps[_snap_i]["shot"]) == k and int(_snaps[_snap_i]["frame"]) <= _drawn:
			var out := str(_snaps[_snap_i]["out"])
			DirAccess.make_dir_recursive_absolute(out.get_base_dir())
			get_viewport().get_texture().get_image().save_png(out)
			print("PLAYER snap %s" % out)
			_snap_i += 1
		_drawn += 1
		if _snap_i >= _snaps.size():
			_finish()
		elif int(_snaps[_snap_i]["shot"]) != k:
			_shot(int(_snaps[_snap_i]["shot"]))
		return
	_drawn += 1
	if _drawn >= int(shots[k]["frames"]):
		_shot(k + 1)


# ----------------------------------------------------------------------------- over the picture

func _overlay() -> void:
	overlay = CanvasLayer.new()
	overlay.layer = 90                  # (over the stage's titles and bubbles, layer 60)
	add_child(overlay)
	card = TextureRect.new()
	card.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	card.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	card.mouse_filter = Control.MOUSE_FILTER_IGNORE
	card.visible = false
	overlay.add_child(card)
	var fonts: Dictionary = plan.get("fonts", {})
	for kind: String in ["text", "italic"]:
		var f := str(fonts.get(kind, ""))
		if f != "" and FileAccess.file_exists(f):
			var ff := FontFile.new()
			if ff.load_dynamic_font(f) == OK:
				_sub_fonts[kind] = ff
	if not _sub_fonts.has("text"):
		_sub_fonts["text"] = FxScript.letters()
	if not _sub_fonts.has("italic"):
		_sub_fonts["italic"] = _sub_fonts["text"]
	sub_box = PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = INK
	sb.set_corner_radius_all(18)
	sb.content_margin_left = 26
	sb.content_margin_right = 26
	sb.content_margin_top = 12
	sb.content_margin_bottom = 16
	sub_box.add_theme_stylebox_override("panel", sb)
	sub_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 2)
	sub_box.add_child(col)
	sub_name = Label.new()
	sub_name.add_theme_font_override("font", _sub_fonts["text"])
	sub_name.add_theme_color_override("font_color", NAME)
	sub_name.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(sub_name)
	sub_text = Label.new()
	sub_text.add_theme_color_override("font_color", PAPER)
	sub_text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sub_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	col.add_child(sub_text)
	sub_box.visible = false
	overlay.add_child(sub_box)


static func _fade(t: float, from: float, to: float, fade: float) -> float:
	if t < from or t > to:
		return 0.0
	return clampf(minf((t - from) / maxf(fade, 0.01), (to - t) / maxf(fade, 0.01)), 0.0, 1.0)


## The card and the subtitle of the shot at `t` seconds into it.
func _lay_over(t: float) -> void:
	var size: Vector2 = get_viewport().get_visible_rect().size
	var s: Dictionary = shots[k]
	var cd: Variant = s.get("card", null)
	if card.texture != null and cd is Dictionary:
		card.position = Vector2.ZERO
		card.size = size
		var a := _fade(t, float(cd.get("from", 0.5)), float(cd.get("to", float(s["seconds"]) - 0.3)), float(cd.get("fade", 0.4)))
		card.modulate.a = a
		card.visible = a > 0.0
	var shown: Dictionary = {}
	for sub: Dictionary in s.get("subs", []):
		if t >= float(sub["from"]) and t <= float(sub["to"]):
			shown = sub
			break
	if shown.is_empty():
		sub_box.visible = false
		return
	var narration: bool = str(shown.get("kind", "line")) == "narration"
	var who := str(shown.get("who", ""))
	sub_name.visible = who != "" and not narration
	sub_name.text = who
	sub_name.add_theme_font_size_override("font_size", int(size.x * 0.034))
	sub_text.text = str(shown.get("text", ""))
	sub_text.add_theme_font_override("font", _sub_fonts["italic" if narration else "text"])
	sub_text.add_theme_font_size_override("font_size", int(size.x * 0.044))
	var max_w: float = size.x * 0.86
	var f: Font = _sub_fonts["italic" if narration else "text"]
	var want: float = f.get_string_size(sub_text.text, HORIZONTAL_ALIGNMENT_LEFT, -1, int(size.x * 0.044)).x + 4.0
	sub_text.custom_minimum_size = Vector2(minf(max_w - 52.0, want), 0.0)
	var sz: Vector2 = sub_box.get_combined_minimum_size()
	sub_box.size = sz
	sub_box.position = Vector2((size.x - sz.x) * 0.5, size.y * 0.90 - sz.y)
	sub_box.modulate.a = _fade(t, float(shown["from"]), float(shown["to"]), 0.15)
	sub_box.visible = true
