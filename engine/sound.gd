extends RefCounted
## SOUND of a scene (docs/framework-tz.md 6.8). The voice comes from the recorded clips (as before); here are the
## music, the sound of the place and the noises of what the heroes do. scene.json:
##   "music": "song.ogg" | {"file": "song.ogg", "volume": -6}   played round and round; quieter while a voice talks
##   "ambience": "forest.ogg" | {"file": ..., "volume": -14}    the place itself: wind, a stove, a street
##   "sfx": false                                               no noises of the heroes' doings (they are on by default)
## Script lines: {"sound": "name"} (a file in the scene's folder, or engine/sounds/<name>.wav),
##               {"music": "other.ogg"} | {"music": "stop"}.
## The noises come by themselves from the engine's events: a foot put down in a walk, a jump, a landing, hands
## meeting in a clap, a blow swung and taken, a thing taken or put down, a spin (engine/sounds, tools/make_sfx.py).
## Every clip's audio goes through the bus "Voice"; while that bus is loud, the music goes down (DUCK dB).
## MUSIC THE HEROES PLAY: an action that plays an instrument says when a note sounds, by what a hand does:
##   "beats": [{ "arm": "arm_l", "on": "down", "sound": "guitar", "min": 0.04, "db": 0 }]
##     on    "down": the hand's lowest point (a strum, a stick on a drum); "up": its highest; "out" / "in": where it
##           turns back going sideways (the bellows of an accordion, a plucked string); "min": arm lengths it must
##           have come since the last turn (a tremble is not a note)
##     sound a name: <name>_<chord>.wav if there is one for the chord playing now (guitar_C, guitar_G...), with
##           _1, _2 ... after it for notes that take turns within it (bass_C_1, bass_C_2); else <name>_1, _2 ... in
##           turn; else <name>.wav
## The chords go round the same for everyone (CHORDS, a chord every BAR seconds): four heroes playing at once
## play together.

const DUCK := -11.0             # dB the music goes down under a voice
const DUCK_ON := -38.0          # dB on the voice bus that counts as talking
const DUCK_SPEED := 30.0        # dB a second the music goes down and comes back
const SWING := ["punch", "haymaker", "uppercut", "kick", "slap", "chop", "slash", "throw", "windmill"]
const TAKE := ["get_hit"]
const CHORDS := ["C", "G", "Am", "F"]
const BAR := 2.0                # seconds a chord lasts

var music: AudioStreamPlayer
var ambience: AudioStreamPlayer
var fx: Dictionary = {}         # name -> AudioStreamPlayer (several at once)
var on := true
var _voice := -1
var _duck := 0.0
var _music_db := 0.0
var _dir := ""
var _host: Node
var _seen: Dictionary = {}      # motion -> events already heard
var _air: Dictionary = {}       # motion -> was in the air
var _clap: Dictionary = {}      # motion -> hands were apart
var _beat: Dictionary = {}      # [motion, arm, on] -> [last turn value, was going that way, turn count]
var _n := 0                     # steps since the start
var _files: Dictionary = {}     # name -> it exists (as a sound file)


func setup(host: Node, spec: Dictionary, scene_dir: String) -> void:
	_host = host
	_dir = scene_dir
	_bus("Voice")
	_bus("Music")
	_bus("Fx")
	_voice = AudioServer.get_bus_index("Voice")
	on = bool(spec.get("sfx", true))
	if spec.has("music"):
		_set_music(spec["music"])
	if spec.has("ambience"):
		var a: Variant = spec["ambience"]
		ambience = _player(str(a["file"]) if a is Dictionary else str(a), "Music", true)
		if ambience != null:
			ambience.volume_db = float(a.get("volume", -14.0)) if a is Dictionary else -14.0
			ambience.play()


static func _bus(name: String) -> void:
	if AudioServer.get_bus_index(name) >= 0:
		return
	AudioServer.add_bus()
	var i := AudioServer.bus_count - 1
	AudioServer.set_bus_name(i, name)
	AudioServer.set_bus_send(i, "Master")


func _set_music(m: Variant) -> void:
	if music != null:
		music.stop()
		music.queue_free()
		music = null
	if m is String and m == "stop":
		return
	music = _player(str(m["file"]) if m is Dictionary else str(m), "Music", true)
	if music != null:
		_music_db = float(m.get("volume", -6.0)) if m is Dictionary else -6.0
		music.volume_db = _music_db
		music.play()


## A player for a sound file: in the scene's folder first, then engine/sounds/<name>.wav.
func _player(file: String, bus: String, loop := false) -> AudioStreamPlayer:
	var path := file
	if not path.is_absolute_path():
		path = _dir.path_join(file)
	if not FileAccess.file_exists(path):
		path = ProjectSettings.globalize_path("res://sounds").path_join(file if file.get_extension() != "" else file + ".wav")
	if not FileAccess.file_exists(path):
		push_warning("sound: no file '%s'" % file)
		return null
	var stream: AudioStream
	match path.get_extension().to_lower():
		"wav":
			stream = AudioStreamWAV.load_from_file(path)
			if loop and stream != null:
				(stream as AudioStreamWAV).loop_mode = AudioStreamWAV.LOOP_FORWARD
				(stream as AudioStreamWAV).loop_end = int((stream as AudioStreamWAV).get_length() * (stream as AudioStreamWAV).mix_rate)
		"ogg":
			stream = AudioStreamOggVorbis.load_from_file(path)
			if stream != null:
				(stream as AudioStreamOggVorbis).loop = loop
		"mp3":
			stream = AudioStreamMP3.load_from_file(path)
			if stream != null:
				(stream as AudioStreamMP3).loop = loop
	if stream == null:
		push_warning("sound: cannot read '%s'" % path)
		return null
	var p := AudioStreamPlayer.new()
	p.stream = stream
	p.bus = bus
	_host.add_child(p)
	return p


## A noise by name, now. `db`: louder or quieter than as recorded.
func play(name: String, db := 0.0) -> void:
	if not fx.has(name):
		var p := _player(name, "Fx")
		if p == null:
			fx[name] = null
			return
		p.max_polyphony = 6
		fx[name] = p
	var player: AudioStreamPlayer = fx[name]
	if player == null:
		return
	player.volume_db = db
	player.play()


## A script line's sound commands.
func command(line: Dictionary) -> void:
	if line.has("sound"):
		play(str(line["sound"]), float(line.get("volume", 0.0)))
	if line.has("music"):
		_set_music(line["music"])


## One step: what the heroes did makes its noise; the music ducks under a voice.
## `heroes`: [[motion, physics, size]]: size = how big the hero is on the screen (quieter when small, far off).
func step(heroes: Array) -> void:
	_n += 1
	if music != null and _voice >= 0:
		var talking: bool = AudioServer.get_bus_peak_volume_left_db(_voice, 0) > DUCK_ON
		_duck = move_toward(_duck, DUCK if talking else 0.0, DUCK_SPEED / 60.0)
		music.volume_db = _music_db + _duck
	if not on:
		return
	for h: Array in heroes:
		var mo: Object = h[0]
		var phys: Object = h[1]
		var db: float = clampf(linear_to_db(float(h[2])), -14.0, 0.0)
		var ev: Array = mo.events
		var from: int = _seen.get(mo, ev.size())
		for i in range(from, ev.size()):
			var e: Array = ev[i]
			match e[2]:
				"foot":
					play("step", db - 6.0)
				"start":
					if e[1] in SWING:
						play("whoosh", db - 3.0)
					elif e[1] in TAKE:
						play("hit", db)
				"grab", "release":
					play("pop", db - 4.0)
		_seen[mo] = ev.size()
		# off the ground and back onto it
		var air: bool = phys.airborne
		if air and not _air.get(mo, false):
			play("jump", db - 4.0)
		elif not air and _air.get(mo, false):
			play("land", db)
		_air[mo] = air
		# a clap: the hands come together while an action of clapping plays
		var clapping := false
		for r: Object in mo.runs:
			if r.id == "clap" and not r.done:
				clapping = true
		if clapping:
			var p: Object = mo.puppet
			var d: float = (p.parts["hand_l"].node as Node2D).global_position.distance_to((p.parts["hand_r"].node as Node2D).global_position)
			var apart: bool = d > 0.9 * float(mo.hand_len["arm_r"])
			if not apart and _clap.get(mo, true):
				play("clap", db)
			_clap[mo] = apart
		_beats(mo, db)


## The notes of an instrument being played: where a hand turns back (see "beats").
func _beats(mo: Object, db: float) -> void:
	for r: Object in mo.runs:
		if r.done or not r.spec.has("beats"):
			continue
		for b: Dictionary in r.spec["beats"]:
			var arm: String = str(b.get("arm", "arm_r"))
			if r.side == "left":
				arm = "arm_l" if arm == "arm_r" else "arm_r"
			var on: String = str(b.get("on", "down"))
			var hand: Node2D = mo.puppet.parts["hand_" + arm.right(1)].node
			var p: Vector2 = hand.global_position
			var body_x: float = mo.puppet.body_position().x
			# the value watched: down the screen, or outward from the body
			var v: float = p.y if on in ["down", "up"] else absf(p.x - body_x)
			var want: float = 1.0 if on in ["down", "out"] else -1.0
			var key := [mo, arm, on]
			var st: Array = _beat.get(key, [v, 0.0, 0, v])
			var going: float = signf(v - float(st[3]))
			st[3] = v
			if going != 0.0:
				if going == -want and float(st[1]) == want and absf(v - float(st[0])) >= float(b.get("min", 0.04)) * mo.arm:
					st[2] = int(st[2]) + 1
					play(_note(str(b.get("sound", "")), int(st[2])), db + float(b.get("db", 0.0)))
				if going != float(st[1]):
					st[0] = v                   # (where it turned: the next note must come this far from here)
				st[1] = going
			_beat[key] = st


## Which file a note of instrument `name` is now (see "beats").
func _note(name: String, count: int) -> String:
	var chord: String = CHORDS[int(_n / 60.0 / BAR) % CHORDS.size()]
	for base: String in ["%s_%s" % [name, chord], name]:
		var k := 0
		while _has("%s_%d" % [base, k + 1]):
			k += 1
		if k > 0:
			return "%s_%d" % [base, (count - 1) % k + 1]
		if base != name and _has(base):
			return base
	return name


func _has(name: String) -> bool:
	if not _files.has(name):
		_files[name] = FileAccess.file_exists(ProjectSettings.globalize_path("res://sounds").path_join(name + ".wav")) or 				FileAccess.file_exists(_dir.path_join(name + ".wav"))
	return _files[name]
