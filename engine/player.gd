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
##   "fonts": {"text": ttf, "italic": ttf, "mono": ttf}
##   "shots": [{ "id", "scene": "<folder with scene.json>", "seconds", "frames",
##               "card": { "image": png, "from", "to", "fade" },
##               "subs": [{ "from", "to", "who": "Корова", "text": "…", "kind": "line" | "narration" }] }]
##   "snaps": [{ "shot": index, "frame": n, "out": "<file.png>" }]      (snap: in order of shot and frame)
## Frames are counted as the site's film counts them (engine/web_boot.gd Film): a shot gives exactly its "frames"
## frames, and its frame 0 is drawn after the stage's first steps, so frame k here is frame k of the site's film.
## Lines printed: "PLAYER shot <id>", "PLAYER snap <file>", "PLAYER done".
##
## THE WINDOW (play) can be stopped and looked at, so a person can show Claude a moment (docs: mechanics-tz 6a):
##   Space pause / play · ←/→ a frame · Shift+←/→ a second · ↑/↓ the previous / next shot · Home the shot's start ·
##   L the shot round and round · S speed 1× / 0.5× / 0.25× · M a mark (playing on) · B the action library on the
##   hero of the moment · H the notes on / off · Esc, Q close.
## The player then drives the stage itself (one step = 1/60 s, as the stage counts): a step back is the shot built
## anew and played up to that step unseen, so what is shown is what the film shows at that moment.
## On a pause it writes (into "state_dir", the world's .tadam/player/): pause.png, the picture as it is without the
## notes, and state.json: where it stands, who says what, what every hero plays, which script lines are at work.
## Play-mode keys in the playlist: "state_dir", "episode", "rev", "script_sha", "lang", "names": {cast key: name},
## "start_step", "start_paused", "rev_file" (tadam writes a new number there when it has written the playlist
## anew after a change in the world: the player reads it again and stands on the same shot and second, paused);
## every shot also "start" (seconds from the episode's start), "remark" and "lines_from" (where the script's own
## lines begin among the scene's, so a scene line is shots[i].camera[n - lines_from] of script.json).

const StageScript := preload("res://stage.gd")
const StageScene := preload("res://stage.tscn")
const FxScript := preload("res://fx.gd")

const INK := Color(0.13, 0.12, 0.10, 0.82)
const PAPER := Color(0.99, 0.97, 0.92)
const NAME := Color(0.98, 0.80, 0.42)
const STEP := 1.0 / 60.0
const SPEEDS: Array[float] = [1.0, 0.5, 0.25]

const WORDS := {
	"ru": {"pause": "ПАУЗА", "play": "идёт", "shot": "план", "of": "из", "s": "с", "frame": "кадр",
		"from_start": "от начала", "says": "говорит", "narration": "за кадром", "still": "стоит", "go": "идёт",
		"turn": "поворачивается", "out": "за кадром", "lines": "строки", "at_work": "в работе", "next": "дальше",
		"waits": "ждёт", "holds": "в позе", "mark": "отметка", "marks": "отметок", "loop": "по кругу", "reread": "сцена перечитана",
		"end": "конец: пробел — с начала, Esc — закрыть", "library": "библиотека",
		"keys": "пробел ▸ · ←→ кадр · Shift ←→ сек · ↑↓ план · L круг · S скорость · M отметка · B библиотека · H скрыть"},
	"en": {"pause": "PAUSED", "play": "playing", "shot": "shot", "of": "of", "s": "s", "frame": "frame",
		"from_start": "from the start", "says": "says", "narration": "narration", "still": "still", "go": "walking",
		"turn": "turning", "out": "off stage", "lines": "lines", "at_work": "at work", "next": "next",
		"waits": "waits", "holds": "holds the pose of", "mark": "mark", "marks": "marks", "loop": "looping", "reread": "scene read again",
		"end": "the end: Space from the start, Esc closes", "library": "library",
		"keys": "Space ▸ · ←→ frame · Shift ←→ second · ↑↓ shot · L loop · S speed · M mark · B library · H hide"},
}

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

# --- the window that can be stopped (play)
var paused := false
var speed := 1.0
var loop_shot := false
var notes_on := true
var _acc := 0.0
var _at_end := false
var _playlist_path := ""
var _rev := ""
var _ticks := 0
var _publish_at := -1.0      # (seconds on the clock) the pause's picture and state are written then
var _capturing := false
var _flash := ""
var _flash_until := 0.0
var _beat_at := 0.0
var marks: Array = []
var _pause: Dictionary = {}  # the moment of the last pause, as written
var hud: CanvasLayer
var hud_box: PanelContainer
var hud_text: Label
var tag: Label               # (playing: the speed and the loop, in a corner)
var _seq: Array = []         # (checks) PLAYER_SEQ: [[tick, key, shift]] pressed by the player itself


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
	_playlist_path = path
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
	if mode == "play":
		_hud()
		_rev = _read_rev()
		_load_audio()
		_seq = _parse_seq(OS.get_environment("PLAYER_SEQ"))
	RenderingServer.frame_post_draw.connect(_on_drawn)
	if mode == "snap":
		if _snaps.is_empty():
			_finish()
			return
		_shot(int(_snaps[0]["shot"]))
	elif mode == "play":
		var at := clampi(int(plan.get("start_step", 0)), 0, _steps_of(int(plan.get("start", 0))))
		_seek(int(plan.get("start", 0)), at)
		if bool(plan.get("start_paused", false)):
			_set_paused(true)
		else:
			_sync_sound()
	else:
		_shot(int(plan.get("start", 0)))
		if mode == "film" and str(plan.get("audio", "")) != "":
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


func _load_audio() -> void:
	if audio != null:
		audio.stop()
		audio.queue_free()
		audio = null
	if str(plan.get("audio", "")) == "":
		return
	var st: AudioStream = _sound(str(plan["audio"]))
	if st != null:
		audio = AudioStreamPlayer.new()
		audio.stream = st
		add_child(audio)


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
	if str(plan.get("actions", "")) != "":             # the world's own actions (its actions/ folder)
		StageScript.boot_args.append("--actions=%s" % plan["actions"])
	stage = StageScene.instantiate()
	add_child(stage)
	move_child(stage, 0)                 # (under the overlay)
	if mode == "play":
		stage.set_physics_process(false)   # (the window steps it itself: it can stop, slow down and go back)
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
	if mode == "play":
		_write_state(false)
	print("PLAYER done")
	get_tree().quit()


func _physics_process(_delta: float) -> void:
	if _over or stage == null:
		return
	if mode == "play":
		_play_tick()
		return
	if _end_at > 0.0 and Time.get_ticks_msec() / 1000.0 >= _end_at:
		_finish()


func _process(_delta: float) -> void:
	if stage != null and not _over:
		_lay_over(int(stage.step_no) / 60.0)
		if mode == "play":
			_hud_draw()


func _unhandled_input(event: InputEvent) -> void:
	if mode != "play" or not (event is InputEventKey) or not event.pressed:
		return
	var e := event as InputEventKey
	var frame_steps: int = maxi(int(round(60.0 / float(plan.get("fps", 30)))), 1)
	match e.keycode:
		KEY_ESCAPE, KEY_Q:
			_finish()
		KEY_SPACE:
			if e.echo:
				return
			if _at_end:
				_at_end = false
				_seek(0, 0)
				_set_paused(false)
			else:
				_set_paused(not paused)
		KEY_RIGHT:
			_set_paused(true)
			_seek_global(_global() + (60 if e.shift_pressed else frame_steps))
		KEY_LEFT:
			_set_paused(true)
			_seek_global(_global() - (60 if e.shift_pressed else frame_steps))
		KEY_UP, KEY_PAGEUP:
			# (as players do: back to this shot's start, and from near it to the shot before)
			_seek(k - 1 if int(stage.step_no) < 30 and k > 0 else k, 0)
			_after_jump()
		KEY_DOWN, KEY_PAGEDOWN:
			if k + 1 < shots.size():
				_seek(k + 1, 0)
				_after_jump()
		KEY_HOME:
			_seek(k, 0)
			_after_jump()
		KEY_L:
			if not e.echo:
				loop_shot = not loop_shot
				_say(_w("loop") + (" ✓" if loop_shot else " ✗"))
		KEY_S:
			if not e.echo:
				speed = SPEEDS[(SPEEDS.find(speed) + 1) % SPEEDS.size()]
				_acc = 0.0
				_say("%s×" % _num(speed))
				_sync_sound()
		KEY_M:
			if not e.echo:
				_mark()
		KEY_B:
			if not e.echo:
				_library()
		KEY_H:
			if not e.echo:
				notes_on = not notes_on


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


# ----------------------------------------------------------------------------- the window that can be stopped

func _steps_of(i: int) -> int:
	return int(round(float(shots[i]["seconds"]) * 60.0)) if i >= 0 and i < shots.size() else 0


## Steps from the episode's start to where the stage stands.
func _global() -> int:
	var g := 0
	for i in k:
		g += _steps_of(i)
	return g + int(stage.step_no)


func _seek_global(g: int) -> void:
	g = maxi(g, 0)
	for i in shots.size():
		var n := _steps_of(i)
		if g <= n or i == shots.size() - 1:
			_seek(i, mini(g, n))
			return
		g -= n


## Stands on step `at` of shot `i`: on along the same shot, else the shot built anew and played up to it unseen.
func _seek(i: int, at: int) -> void:
	i = clampi(i, 0, shots.size() - 1)
	at = clampi(at, 0, _steps_of(i))
	_at_end = false
	var quiet := AudioServer.is_bus_mute(0)
	AudioServer.set_bus_mute(0, true)          # (the heroes' noises of the steps played unseen are not heard)
	if i != k or stage == null or at < int(stage.step_no):
		_shot(i)
	while int(stage.step_no) < at:
		stage._physics_process(STEP)
	AudioServer.set_bus_mute(0, quiet)
	_sync_sound()
	if paused:
		_publish_soon()


func _after_jump() -> void:
	if paused:
		_publish_soon()
	else:
		_sync_sound()


func _play_tick() -> void:
	_ticks += 1
	while not _seq.is_empty() and int(_seq[0][0]) <= _ticks:
		_run_seq(_seq.pop_front())
	if _ticks % 30 == 0:
		var rev := _read_rev()
		if rev != _rev:
			_rev = rev
			_reload()
	var now := Time.get_ticks_msec() / 1000.0
	if _publish_at > 0.0 and now >= _publish_at and not _capturing:
		_publish_at = -1.0
		_publish()
	if now >= _beat_at:
		_beat_at = now + 2.0
		_write_state(true)
	if paused:
		return
	_acc += speed
	while _acc >= 1.0 and not paused:
		_acc -= 1.0
		_one_step()


func _one_step() -> void:
	if int(stage.step_no) >= _steps_of(k):
		if loop_shot:
			_seek(k, 0)
			return
		if k + 1 < shots.size():
			_shot(k + 1)
			return
		_at_end = true                 # the last picture stays, paused: Space plays it from the start
		_set_paused(true)
		_say(_w("end"), 4.0)
		return
	stage._physics_process(STEP)


func _set_paused(on: bool) -> void:
	if on == paused:
		return
	paused = on
	_acc = 0.0
	_sync_sound()
	if paused:
		_publish_soon()


## The episode's sound follows the picture: heard at 1× while playing, from the very moment; else silent.
func _sync_sound() -> void:
	var live := not paused and is_equal_approx(speed, 1.0)
	AudioServer.set_bus_mute(0, not live)
	if audio == null:
		return
	if live:
		audio.play(float(shots[k].get("start", 0.0)) + int(stage.step_no) / 60.0)
	elif audio.playing:
		audio.stop()


func _publish_soon() -> void:
	_publish_at = Time.get_ticks_msec() / 1000.0 + 0.25      # (a key held down: written once it lets go)


## (for checking the window itself, as engine/viewer.gd does with VIEWER_SEQ: no screen, no hands needed)
## PLAYER_SEQ="30:right,40:shift+left,60:space,90:m,120:shot=<file.png>,150:quit": keys pressed at those ticks of
## the window (60 a second); "shot=" saves the window as it is, the notes over it included.
static func _parse_seq(text: String) -> Array:
	var out: Array = []
	for part: String in text.split(",", false):
		var at := part.find(":")
		if at > 0:
			out.append([int(part.substr(0, at)), part.substr(at + 1).strip_edges()])
	out.sort_custom(func(x: Array, y: Array) -> bool: return x[0] < y[0])
	return out


func _run_seq(item: Array) -> void:
	var what: String = item[1]
	if what.begins_with("shot="):
		var out := what.trim_prefix("shot=")
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(out)
		print("PLAYER seq shot %s" % out)
		return
	if what == "quit":
		_finish()
		return
	var keys := {"right": KEY_RIGHT, "left": KEY_LEFT, "up": KEY_UP, "down": KEY_DOWN, "home": KEY_HOME,
		"space": KEY_SPACE, "l": KEY_L, "s": KEY_S, "m": KEY_M, "b": KEY_B, "h": KEY_H}
	var e := InputEventKey.new()
	e.shift_pressed = what.begins_with("shift+")
	e.keycode = keys.get(what.trim_prefix("shift+"), KEY_NONE)
	e.pressed = true
	_unhandled_input(e)
	print("PLAYER seq %s at %s %d" % [what, shots[k].get("id", k), int(stage.step_no)])


# ----------------------------------------------------------------------------- what is going on now

func _w(key: String) -> String:
	var lang := str(plan.get("lang", "ru"))
	return str(WORDS.get(lang, WORDS["en"]).get(key, key))


static func _num(x: float) -> String:
	return ("%.2f" % x).rstrip("0").rstrip(".")


func _name_of(id: String) -> String:
	return str(plan.get("names", {}).get(id, id))


## What every hero is doing at this step: its actions (as the library names them), walking, turning.
func _heroes() -> Array:
	var out: Array = []
	for id: String in stage.actors:
		var a: Variant = stage.actors[id]
		var acts: Array = []
		for r: Variant in a.motion.runs:
			if not r.done and not str(r.id).begins_with("_"):
				acts.append({"id": str(r.id), "phase": int(r.i) + 1, "phases": r.phases.size(),
					"t": snappedf(float(r.t), 0.01)})
		var rec := {"key": id, "name": _name_of(id), "actions": acts, "going": not a.going.is_empty(),
			"turning": not a.turning.is_empty(), "view": str(a.view), "off_stage": float(a.out) != 0.0}
		var held := _held(id)
		if acts.is_empty() and held != "":
			rec["holds"] = held             # (an action over leaves the body as it put it: its last pose)
		out.append(rec)
	return out


## The action whose last pose the hero is left in: the latest "do" of the shot for it, when that is over.
func _held(id: String) -> String:
	var best := -1
	var act := ""
	for line: Dictionary in stage.spec.get("script", []):
		if str(line.get("who", "")) == id and line.has("do") and line.has("_ran") and int(line["_ran"]) > best:
			best = int(line["_ran"])
			act = str(line["do"])
	if act == "":
		return ""
	var r: Variant = stage.actors[id].playing.get(act, null)
	return act if r != null and r.done else ""


## The shot's lines that have run, whether each is still at work, and the next ones.
func _lines() -> Array:
	var out: Array = []
	var from := int(shots[k].get("lines_from", 0))
	var script: Array = stage.spec.get("script", [])
	var now := int(stage.step_no)
	for n in script.size():
		var line: Dictionary = script[n]
		if n < from:
			continue               # (the kit's own lines: a prop shown in the hand)
		var shown := {}
		for key: String in line:
			if not key.begins_with("_"):
				shown[key] = line[key]
		var rec := {"n": n - from, "line": shown}
		if line.has("_ran"):
			rec["ran"] = snappedf(int(line["_ran"]) / 60.0, 0.01)
			rec["status"] = "at_work" if _at_work(line, now) else "done"
			if rec["status"] == "done" and line.has("do") and _held(str(line.get("who", ""))) == str(line["do"]):
				rec["status"] = "holds"
		elif line.has("after") and not line.has("_step"):
			rec["status"] = "waits"
		else:
			rec["status"] = "next"
			rec["due"] = snappedf(int(line.get("_step", 0)) / 60.0, 0.01)
		out.append(rec)
	return out


func _at_work(line: Dictionary, now: int) -> bool:
	var a: Variant = stage.actors.get(str(line.get("who", "")), null)
	if a != null and line.has("do"):
		var r: Variant = a.playing.get(str(line["do"]), null)
		if r != null and not r.done:
			return true
	if a != null and line.has("go") and not a.going.is_empty():
		return true
	if a != null and (line.has("turn") or line.has("facing")) and not a.turning.is_empty():
		return true
	if line.has("say"):
		return now < int(line["_ran"]) + int(float(line.get("for", 2.5)) * 60.0)
	if line.has("camera") or line.has("time"):
		return now < int(line["_ran"]) + int(float(line.get("time", 0.0)) * 60.0)
	return false


## Who is heard now: the subtitle on the screen.
func _speaking() -> Dictionary:
	var t: float = int(stage.step_no) / 60.0
	for sub: Dictionary in shots[k].get("subs", []):
		if t >= float(sub["from"]) and t <= float(sub["to"]):
			return {"who": str(sub.get("who", "")), "text": str(sub.get("text", "")), "kind": str(sub.get("kind", "line"))}
	return {}


func _where() -> Dictionary:
	var s: Dictionary = shots[k]
	var t: float = int(stage.step_no) / 60.0
	var fps := float(plan.get("fps", 30))
	return {"shot": str(s.get("id", k)), "index": k, "shots": shots.size(), "remark": str(s.get("remark", "")),
		"seconds": float(s["seconds"]), "at": snappedf(t, 0.01), "step": int(stage.step_no),
		"frame": int(floor(t * fps + 0.001)), "from_start": snappedf(float(s.get("start", 0.0)) + t, 0.01)}


func _moment() -> Dictionary:
	var m := _where()
	m["speaking"] = _speaking()
	m["heroes"] = _heroes()
	m["lines"] = _lines()
	return m


# ----------------------------------------------------------------------------- what is written for Claude

func _state_dir() -> String:
	return str(plan.get("state_dir", ""))


func _write_state(running: bool) -> void:
	if _state_dir() == "" or stage == null:
		return
	DirAccess.make_dir_recursive_absolute(_state_dir())
	var st := {"running": running, "paused": paused, "speed": speed, "loop": loop_shot,
		"updated": Time.get_datetime_string_from_system(true, false) + "Z", "unix": Time.get_unix_time_from_system(),
		"episode": str(plan.get("episode", "")), "rev": _rev, "script_sha": str(plan.get("script_sha", "")),
		"lang": str(plan.get("lang", "")), "now": _where(), "pause": _pause, "marks": marks,
		"library": _state_dir().path_join("library.json")}
	var tmp := _state_dir().path_join("state.json.part")
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		return
	f.store_string(JSON.stringify(st, " "))
	f.close()
	DirAccess.rename_absolute(tmp, _state_dir().path_join("state.json"))


## The picture as it is now, without the notes over it.
func _capture(out: String) -> void:
	_capturing = true
	var was := hud.visible
	hud.visible = false
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(out.get_base_dir())
	get_viewport().get_texture().get_image().save_png(out)
	hud.visible = was
	_capturing = false


func _publish() -> void:
	if not paused or stage == null:
		return
	var m := _moment()
	if _state_dir() != "":
		var png := _state_dir().path_join("pause.png")
		await _capture(png)
		m["png"] = png
	_pause = m
	_write_state(true)
	print("PLAYER pause %s %.2f" % [m["shot"], m["at"]])


func _mark() -> void:
	var m := _moment()
	m["n"] = marks.size() + 1
	if _state_dir() != "" and not _capturing:
		var png := _state_dir().path_join("mark-%d.png" % m["n"])
		await _capture(png)
		m["png"] = png
	marks.append(m)
	_write_state(true)
	_say("%s %d · %s %.2f %s" % [_w("mark"), m["n"], m["shot"], m["at"], _w("s")])
	print("PLAYER mark %d %s %.2f" % [m["n"], m["shot"], m["at"]])


## The action library (engine/viewer.tscn) in a window of its own, on the hero of the moment and what it plays.
func _library() -> void:
	var hs := _heroes()
	if hs.is_empty():
		return
	var who: Dictionary = hs[0]
	var talking := _speaking()
	for h: Dictionary in hs:
		if not h["actions"].is_empty() and who["actions"].is_empty():
			who = h
		if talking.get("who", "") != "" and h["name"] == talking["who"]:
			who = h
			break
	var puppet := ""
	for d: Dictionary in stage.spec.get("actors", []):
		if str(d.get("id", "")) == who["key"]:
			puppet = str(d.get("puppet", ""))
	if puppet == "":
		return
	var args := PackedStringArray(["--path", ProjectSettings.globalize_path("res://"), "--resolution", "1320x820",
		"res://viewer.tscn", "--", "--hero=" + puppet])
	if not who["actions"].is_empty():
		args.append("--action=" + str(who["actions"][0]["id"]))
	if _state_dir() != "":
		args.append("--chosen=" + _state_dir().path_join("library.json"))
	OS.create_process(OS.get_executable_path(), args)
	_say("%s: %s" % [_w("library"), who["name"]])


# ----------------------------------------------------------------------------- the scene read again

func _read_rev() -> String:
	var f := str(plan.get("rev_file", ""))
	return FileAccess.get_file_as_string(f).strip_edges() if f != "" and FileAccess.file_exists(f) else ""


## tadam wrote the playlist anew (the script or a picture changed): the same shot (by its id) and second, paused.
func _reload() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(_playlist_path))
	if not (parsed is Dictionary) or (parsed.get("shots", []) as Array).is_empty():
		return
	var id := str(shots[k].get("id", ""))
	var at := int(stage.step_no)
	var audio_was := str(plan.get("audio", ""))
	plan = parsed
	shots = plan["shots"]
	var i := clampi(k, 0, shots.size() - 1)
	for j in shots.size():
		if str(shots[j].get("id", "")) == id:
			i = j
	if str(plan.get("audio", "")) != audio_was:
		_load_audio()
	paused = true
	_acc = 0.0
	k = -1                       # (built anew even when it is the same shot)
	_seek(i, at)
	_sync_sound()
	_publish_soon()
	_say(_w("reread"), 3.0)
	print("PLAYER reread %s %.2f" % [shots[i].get("id", i), at / 60.0])


# ----------------------------------------------------------------------------- over the picture

func _say(text: String, secs := 1.6) -> void:
	_flash = text
	_flash_until = Time.get_ticks_msec() / 1000.0 + secs


func _hud() -> void:
	hud = CanvasLayer.new()
	hud.layer = 95
	add_child(hud)
	hud_box = PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.10, 0.09, 0.08, 0.86)
	sb.content_margin_left = 12
	sb.content_margin_right = 12
	sb.content_margin_top = 8
	sb.content_margin_bottom = 10
	hud_box.add_theme_stylebox_override("panel", sb)
	hud_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hud.add_child(hud_box)
	hud_text = Label.new()
	hud_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hud_text.add_theme_color_override("font_color", PAPER)
	var mono := str(plan.get("fonts", {}).get("mono", ""))
	if mono != "" and FileAccess.file_exists(mono):
		var ff := FontFile.new()
		if ff.load_dynamic_font(mono) == OK:
			hud_text.add_theme_font_override("font", ff)
	hud_box.add_child(hud_text)
	tag = Label.new()
	tag.add_theme_color_override("font_color", NAME)
	tag.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	tag.add_theme_constant_override("outline_size", 6)
	hud.add_child(tag)


func _hud_draw() -> void:
	if _capturing:
		return
	var size: Vector2 = get_viewport().get_visible_rect().size
	var fs := clampi(int(size.x * 0.03), 11, 22)
	hud_text.add_theme_font_size_override("font_size", fs)
	tag.add_theme_font_size_override("font_size", fs + 2)
	var flash := _flash if Time.get_ticks_msec() / 1000.0 < _flash_until else ""
	var bits: Array = []
	if not is_equal_approx(speed, 1.0):
		bits.append("%s×" % _num(speed))
	if loop_shot:
		bits.append(_w("loop"))
	if marks.size() > 0:
		bits.append("%s: %d" % [_w("marks"), marks.size()])
	tag.text = flash if flash != "" else " · ".join(bits)
	tag.position = Vector2(12, size.y - fs * 2.6)
	tag.visible = tag.text != "" and (not paused or not notes_on)
	hud_box.visible = paused and notes_on
	if not hud_box.visible:
		return
	var m := _moment()
	var L: Array = []
	L.append("%s · %s %s (%d/%d) · %s %s / %s %s · %s %d · %s %s %s" % [_w("pause"), _w("shot"), m["shot"],
		int(m["index"]) + 1, int(m["shots"]), _num(m["at"]), _w("s"), _num(m["seconds"]), _w("s"), _w("frame"),
		int(m["frame"]), _w("from_start"), _num(m["from_start"]), _w("s")])
	if str(m["remark"]) != "":
		L.append("«%s»" % m["remark"])
	var sp: Dictionary = m["speaking"]
	if not sp.is_empty():
		var who: String = _w("narration") if sp["kind"] == "narration" else str(sp["who"])
		L.append("%s — %s" % [who, sp["text"]])
	for h: Dictionary in m["heroes"]:
		var doing: Array = []
		for a: Dictionary in h["actions"]:
			doing.append("%s %d/%d" % [a["id"], a["phase"], a["phases"]])
		if h["going"]:
			doing.append(_w("go"))
		if h["turning"]:
			doing.append(_w("turn"))
		if h["off_stage"]:
			doing.append(_w("out"))
		if h.has("holds"):
			doing.append("%s %s" % [_w("holds"), h["holds"]])
		L.append("%s: %s" % [h["name"], ", ".join(doing) if not doing.is_empty() else _w("still")])
	var work: Array = []
	for ln: Dictionary in m["lines"]:
		if ln["status"] == "at_work" or ln["status"] == "holds":
			work.append("[%d] %s" % [ln["n"], _short(ln["line"])])
	if not work.is_empty():
		L.append("%s %s: %s" % [_w("lines"), _w("at_work"), "; ".join(work)])
	if flash != "":
		L.append("» " + flash)
	L.append(_w("keys"))
	hud_text.text = "\n".join(L)
	hud_box.position = Vector2.ZERO
	hud_box.size = Vector2(size.x, 0)
	hud_text.custom_minimum_size = Vector2(size.x - 24, 0)
	hud_box.size = Vector2(size.x, hud_box.get_combined_minimum_size().y)


static func _short(line: Dictionary) -> String:
	var parts: Array = []
	for key: String in line:
		if key != "at":
			parts.append("%s=%s" % [key, str(line[key])])
	var s := " ".join(parts)
	return s if s.length() <= 48 else s.substr(0, 47) + "…"


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
