extends Node2D
## Plays a scene written as DATA: a background, actors (puppets, with a recorded face or their own), and a script
## of commands in time. This is the first cut of the command language: a script says WHAT happens ("at 3.0 the
## right hand waves, the head tilts, show the shovel"), never an angle or a pixel, and the same script fits any
## puppet because every place is measured in that puppet's own arm and leg lengths.
##
## scene.json (in its own folder, e.g. ../scenes/forest_stump/):
##   "background": "bg.png"            picture in the scene's folder (or an absolute path, like every picture and sound
##                                     a scene names), scaled to cover the stage (optional)
##   "floor": 0.86                     where soles stand, share of the stage height
##   "seconds": 12                     how long the scene is
##   "tint": [0.8, 0.88, 1.0]          colour of the light on the actors (optional)
##   "world": "picture"                the world is the whole background picture (a wide one gives room to walk and
##                                     for a 16:9 picture); without it the world is 720 x 1280, the picture cropped to it
##   "format": "9:16" | "1:1" | "16:9" the shape of the film; the camera fits the world into it
##   "camera": { "camera": "wide" }    how the scene starts; then camera lines in the script (engine/camera.gd)
##   "ground": { "far": 0.66, "far_scale": 0.65, "tilt": 0.7 }   the DEPTH of the scene (engine/space.gd): a hero
##                                     deeper in is smaller and higher up, and is drawn behind those nearer
##   "haze": [r, g, b, amount]         heroes and things fade towards this colour with depth (all the way back: amount)
##   "points": { "door": { "x": 0.62, "y": 0.70, "face": "left" } }   named places ON THE GROUND, shares of the
##                                     stage (where a foot stands there); commands go to them by name
##   "pieces": [{ "id": "crate", "image": "crate.png", "rect": [x, y, w, h], "base": 0.71 }]   SET PIECES: parts of
##                                     the background cut out (tools/cut_piece.py), drawn over it in place, sorted in
##                                     depth with the heroes by `base` (where it stands on the ground, share of the
##                                     stage height; "front": true = always in front, a foreground frame)
##   "actors": [{ "id": "hag", "puppet": "hag", "x": 0.38, "height": 0.42, "clip": "head.ogv", ("depth" | "y" | "at")
##                "props": { "shovel": { "image": "shovel.png", "hand": "right", "length": 1.6, "grip": 0.72 } } }]
##         x = share of the stage width, height = neck-to-sole as a share of the stage height (at the front edge),
##         depth = share of the ground's depth (0 front, 1 far line), or y = where its feet are on the screen, or
##         at = a point's name,
##         clip = a recorded head (lab/head_clip.py), in the scene's folder or an absolute path
##         mouth = a recorded MOUTH only (lab/mouth_clip.py): the hero stays painted, a real mouth talks on its face
##         speech = [[from, to], ...] seconds: a line with NO recording (the kit's local player): the painted mouth
##                  (the head's "open" drawing, if the puppet has one) opens and shuts in these phrases, and
##                  { "phrase": N } lines wait for them as for a recorded voice's
##   "life": [...]                     the LIVING background: behaviours on set pieces and places (engine/life.gd)
##   "light": {"at": [x, y]}           a light: heroes cast shadows of their shape away from it and get a lit edge
##   "grade": "evening", "vignette": 0.3   the colour of the whole picture (engine/light.gd)
##   "music", "ambience", "sfx"        sound (engine/sound.gd)
##   "hands": "stump" (default)        hands with no fingers, one drawing for every pose: the top of the painted hand,
##            | "one" | "none" | "drawn" rounded off; or the painted hand only; or none; or as painted (puppet.gd)
##   "script": [{ "at": 1.5, "who": "hag", ...commands }]      `at` in seconds ("time": "share" -> 0..1 of the scene);
##              "who": "all" = every actor
## WHEN a line happens, four ways (docs/framework-tz.md 7.1); "delay": seconds after that:
##   "at": seconds
##   "after": an action ("jump", "go", "turn", "play", "say", "take", "put"...): once that hero ("of": another hero,
##            else the line's "who") has finished it, the first time after "at" (0 if not given);
##            "after": "#name": once the line with "label": "name" has finished what it started
##   "phrase": N   as the N-th phrase of a recorded voice begins ("end": true: as it ends); the voice of "voice" or
##            of "who" (tadam.phrases finds the phrases: <clip>.phrases.json)
##   "beat": N     on the N-th beat of the music ("music": {"file", "bpm", "offset"}: tools/bpm.py finds them)
## A dance ("beat_rate" in its file) goes at the music's tempo when the music has a "bpm".
## Commands of a line (any of them together):
##   "do": an ACTION by name (engine/actions/<name>.json: wave, hips, think, bow, jump, dance_twist...), with its
##         params beside it: "side": "left" | "right" | "both", "energy": 1.3, "speed": 0.8, "duration": 2.0
##         (motion.gd plays it; actions on different parts of the body go on together)
##   "stop": an action by name, or "all": let it go (back to rest, or to its own return)
##   "sit": a point with a "seat" (furniture): go there, turn as the point says, sit down and stay ("for": seconds)
##   "stand": true: get up from sitting
##   "turn": "left" | "right" | "front" | "back": the hero turns (its side view, puppets/<name>/side, faces left or
##           right; its back view is puppets/<name>/back). The pose, what it holds and its recorded face go with it.
##   "go": x as a share of the stage width (with "depth" or "y": also into or out of the depth), or a point's name:
##         the hero turns that way, walks there ("speed": leg lengths a second;
##         "style": run | sneak | waddle | march | drunk | skip, or walk)
##         and turns to the front again ("then": "keep" stays in profile);
##         "go": another hero's id: up to where a blow lands on it, facing it;
##         "go": "out_left" | "out_right": off the stage over that edge (an actor with "x": "out_left" starts there,
##         unseen, and comes in with any "go")
##   "to": a hero's id, beside a blow ("do": "punch", ...): first up to it if it is not within reach, then the blow
##   "spin": times round (a spin through every view the hero has; "time": seconds a round)
##   An action made for one view ("view": "side" in its file, like sit) turns the hero to that view first; one
##   that works at the floor ("low_view": "side": take, put, lift) does it when the thing is on the floor.
##   "play": an instrument (guitar | balalaika | drum | accordion | bass | pipe, or a card of the scene's own): the
##         hero gets it and plays it ("for": seconds; "energy", "speed"); "play": "off" puts it away. The notes
##         come from the hands (engine/sound.gd "beats"), in time with everyone else playing
##   "with": another hero, beside an action made for TWO ("pair" in its file: handshake, high_five, side_hug, push,
##         dance_pair): the hero goes up to the other one (as far as the pair needs, by both bodies' widths), and both
##         do their parts at once, each with its hand nearest the other ("@partner" points: its hand, shoulders, waist)
##   "say": text (a bubble over the hero; "for": seconds), "stars": seconds; and lines without "who": "title",
##   "subtitle", "flash", "confetti" (engine/fx.gd), "grade" ("time": seconds), "sound", "music"
##   older, still understood: "hands" / "left" / "right": a hand place by name (see PLACES); "head": tilt degrees;
##   "lean": body lean degrees; "bow": chest degrees; "do": "stamp_left" | "stamp_right"
##   "show": prop id   "hide": prop id
##
## run:   godot --path engine res://stage.tscn -- --scene=<folder> [--clip=<file>] [--seconds=<n>]
##        [--font=<file.ttf>]   the letters of bubbles and titles (the kit passes its own OFL font; engine/fx.gd)
##        [--board-preview]     the site's look before a face is recorded: the head as the site enlarges it and a
##                              flat placeholder where the face will be (engine/video_head.gd preview)
## a whole episode, shot after shot (the kit's `tadam play / frames / film`): res://player.tscn (engine/player.gd)
## live:  ... -- --scene=<folder> --live=9080 [--live-host=0.0.0.0]   driven from outside (engine/live.gd)
## check: ... -- --scene=<folder> --check   plays it through as fast as it can, unseen, and prints one line
##        "CHECK {json}": where a hero talks off the picture, with its back to us, or with its recorded face too
##        small (tools/check_scene.py runs it after its own checks of the file)
## film:  add  --write-movie out.avi --fixed-fps 60 --quit-after <seconds * 60>  before res://stage.tscn

const Puppet := preload("res://puppet.gd")
const BodyPhysics := preload("res://body_physics.gd")
const VideoHead := preload("res://video_head.gd")
const VideoMouth := preload("res://video_mouth.gd")
const Motion := preload("res://motion.gd")
const Items := preload("res://items.gd")
const Life := preload("res://life.gd")
const Light := preload("res://light.gd")
const Sound := preload("res://sound.gd")
const Fx := preload("res://fx.gd")
const Space := preload("res://space.gd")
const Cam := preload("res://camera.gd")
const Live := preload("res://live.gd")
const Focus := preload("res://focus.gd")

const SIZE := Vector2(720, 1280)
const TURN_TIME := 0.2        # seconds a turn takes
const TURN_SWAP := 0.4         # ...the drawing changes this far into it: at the bottom of the dip
const STRIKE_REACH := 0.92     # arm lengths: how much of the arm a blow at another hero is thrown from (see _strike_gap)
const RIM_PX := 3.5             # screen px the lit edge of a hero reaches in from its outline
const OUT_MARGIN := 0.9        # leg lengths beyond the edge of the world a hero stands when it is off the stage
const SPIN_TIME := 0.8         # seconds a spin ("spin") takes to go once round
const TURN_DIP := 0.07         # leg lengths the hero sinks into a turn and comes up out of it
const TURN_BREATH := 0.06      # how much narrower it is at the change (a breath, not a card turned edge on)
const TURN_NARROW := 0.58      # (the old turn, "turn_style": "squeeze": the narrowest, share of its width)
const FACE_MIN := 0.12        # a recorded face smaller than this share of the picture's height is not seen

## Where a hand goes, by name: x outward from its shoulder and y down, in arm lengths; then how it lives there:
## [x, y, drift x, drift y, speed (radians per step), wrist swing in degrees].
## The arm itself stays where it is; what waves, wags and beckons is the HAND, turning at the wrist, about twice a
## second. Only rubbing and shooing move the arm, a little and in a straight line. An arm shaken as a whole, or
## led in circles, looks like a rag.
const PLACES := {
	"down": [0.10, 0.94, 0.0, 0.0, 0.0, 0.0],
	"hips": [0.04, 0.60, 0.0, 0.0, 0.0, 0.0],
	"wave": [0.44, -0.68, 0.0, 0.0, 0.21, 24.0],
	"up": [0.50, -0.82, 0.02, 0.0, 0.19, 14.0],
	"wag": [0.50, -0.42, 0.0, 0.0, 0.24, 20.0],
	"wide": [0.85, 0.20, 0.0, 0.0, 0.0, 0.0],
	"beckon": [0.50, -0.02, 0.0, 0.0, 0.17, 28.0],
	"point": [0.95, -0.06, 0.0, 0.0, 0.0, 0.0],
	"chest": [-0.28, 0.24, 0.0, 0.0, 0.0, 0.0],
	"rub": [-0.34, 0.36, 0.03, 0.0, 0.26, 8.0],
	"show": [0.46, -0.30, 0.0, 0.0, 0.0, 0.0],
	"shoo": [0.70, 0.05, 0.04, 0.0, 0.22, 22.0],
}
const CROSS_REACH := 0.80        # how far out (arm lengths) a hand is when its elbow has to change sides


class Actor:
	var id: String
	var dir := ""                     # the hero's folder
	var height := 0.45                # neck to sole, share of the stage height
	var puppet: Puppet                # the view shown now, its physics and motion
	var phys: BodyPhysics
	var motion: Motion
	var view := "front"               # "front" | "back" | "side_r" | "side_l"
	var views: Dictionary = {}        # view -> {puppet, phys, motion, k}
	var arm := 100.0
	var leg := 100.0
	var props: Dictionary = {}        # prop id -> Sprite2D
	var prop_defs: Dictionary = {}    # prop id -> [def, Image]
	var playing: Dictionary = {}      # action id -> its run
	var clip := ""
	var head: Node2D                  # the recorded face, if any
	var player: VideoStreamPlayer
	var sound := true                 # its recorded clip is heard (several heroes with one clip: only one of them)
	var mouth_clip := ""              # a recorded MOUTH (lab/mouth_clip.py): the painted face keeps everything else
	var mouth: Node2D
	var mouth_player: VideoStreamPlayer
	var speech: Array = []            # [[from s, to s], ...]: a line with no recording; the painted mouth talks
	var turning: Dictionary = {}      # a turn under way: {t, to}
	var after: Array = []             # what to do once the turn is over: [command lines]
	var going: Dictionary = {}        # a "go" under way: {stage, dx, then, speed}
	var measured: Dictionary = {}     # what earlier views measured (they are summed up at the end)
	var back_to: Array = []           # [run, view]: when that action is over, turn back to that view
	var instruments: Array = []       # ids of the items it plays on now (an instrument, and its drumsticks)
	var partner: Actor = null         # the hero it does something with now ("with": a handshake, a hug)
	var bias := 0.0                   # drawn in front of others at the same depth when less (an arm over a shoulder)
	var layer: CanvasLayer            # everything of this hero is drawn here; its transform is its depth
	var z := 0.0                      # depth on the ground, frame px (space.gd)
	var shadow: Node2D
	var cast: Dictionary = {}         # its shadow on the ground away from the scene's light (engine/light.gd)
	var rim: ShaderMaterial           # ...and the lit edge on the side facing it
	var out := 0.0                    # off the stage: -1 beyond its left edge, 1 beyond its right one (not drawn)
	var leaving := 0.0                # walking out over that edge now (-1 / 1)
	var entering := false             # walking in from beyond an edge now: the sides stay open until it is there


static var _actions: Dictionary = {}


## The action library: engine/actions/*.json, read once.
static func actions() -> Dictionary:
	if _actions.is_empty():
		var dir := ProjectSettings.globalize_path("res://actions")
		if not DirAccess.dir_exists_absolute(dir):
			dir = "res://actions"
		for f in DirAccess.get_files_at(dir):
			if f.ends_with(".json"):
				var a: Variant = JSON.parse_string(FileAccess.get_file_as_string(dir.path_join(f)))
				if a is Dictionary:
					_actions[a["id"]] = a
	return _actions


static var preset: Dictionary = {}
## Arguments handed over by a boot scene (the web build has no command line): the same --scene=… --seconds=… lines.
static var boot_args: PackedStringArray = []
var scene_dir := ""
var spec: Dictionary = {}
var actors: Dictionary = {}
var script_lines: Array = []
var floor_y := 1100.0
var seconds := 10.0
var step_no := 0
var _next := 0
var _waiting: Array = []              # lines waiting for something to finish ("after")
var _due: Array = []                  # lines whose time came from such a thing: [step, line]
var _events: Array = []               # [step, actor id, what it finished: an action id, "go", "turn", "say", "play"]
var _labels: Dictionary = {}          # "name" -> [actor id, what the line started, step]
var _logged: Dictionary = {}          # runs already logged as finished
var _was: Dictionary = {}             # actor id -> [going, turning] a step ago
var _phrase_cache: Dictionary = {}    # clip -> [[start, end], ...]
var _live_port := 0
var _live_host := "127.0.0.1"
var live: Live = null                 # --live=<port>: driven from outside as it plays (engine/live.gd)
var checking := false                 # --check: played through unseen, problems reported (tools/check_scene.py)
var _talk: Array = []                 # [actor id, from step, to step]: a bubble over it
var _problems: Dictionary = {}        # "kind|actor" -> [[from s, to s], ...]
var items: Items = null
var space: Space
var points: Dictionary = {}           # name -> {x, y, ...} (shares of the stage, on the ground)
var pieces: Array = []                # [{id, layer, z}]
var _piece_nodes: Dictionary = {}     # piece id -> {holder, sprite, rect} (engine/life.gd moves them)
var life: Life                        # the living background
var _covered: Dictionary = {}         # "element/hero" already reported covering a face
var light: Light                      # colour of the picture, the light's shadows and rims (engine/light.gd)
var sound: Sound                      # music, the place's sound, the heroes' noises (engine/sound.gd)
var fx: Fx                            # bubbles, titles, flash, confetti, stars (engine/fx.gd)
var _back: CanvasLayer                # the background, behind everything
var _backdrops: Array = []            # [{layer, scale}]: FAR layers behind the background ("backdrops")
var _item_layers: Dictionary = {}     # item id -> its own layer while it is free
var _haze := Color(0, 0, 0, 0)
var world := SIZE                     # the scene's world, px (positions are shares of it)
var camera: Cam
var camera_on := true                 # (the viewer shows the world as it is)
var _cam_line: Dictionary = {"camera": "wide"}
var focus: Focus                      # depth of field: what is sharp, what is soft (engine/focus.gd)
var parallax := false                 # "parallax": true: nearer layers slide faster when the camera moves
var board_preview := false            # --board-preview: the site's face-in-a-board look, a placeholder face


## A file the scene names (background, pieces, backdrops, props, item cards): an absolute path (also res:// and
## user://) is taken as it is, anything else is in the scene's folder. The studio kit (`tadam`) writes its scenes into
## the world folder's .tadam/ with absolute paths to the pictures, so a scene and its pictures may be on different
## drives (Windows) or anywhere at all; the server writes its own scenes and never passes a sender's path through.
func _scene_file(p: String) -> String:
	if p.is_absolute_path():
		return p
	return scene_dir.path_join(p)


func _ready() -> void:
	var clip_arg := ""
	var seconds_arg := 0.0
	for a in OS.get_cmdline_user_args() + boot_args:
		if a.begins_with("--scene="):
			scene_dir = a.trim_prefix("--scene=")
		elif a.begins_with("--clip="):
			clip_arg = a.trim_prefix("--clip=")
		elif a.begins_with("--seconds="):
			seconds_arg = float(a.trim_prefix("--seconds="))
		elif a == "--check":
			checking = true
		elif a.begins_with("--font="):
			Fx.font_path = a.trim_prefix("--font=")
		elif a == "--board-preview":
			board_preview = true
		elif a.begins_with("--live="):
			_live_port = int(a.trim_prefix("--live="))
		elif a.begins_with("--live-host="):
			_live_host = a.trim_prefix("--live-host=")
	# (a scene handed over ready-made, by the viewer, instead of a file)
	var parsed: Variant = preset if not preset.is_empty() else JSON.parse_string(FileAccess.get_file_as_string(scene_dir.path_join("scene.json")))
	if not (parsed is Dictionary):
		push_error("stage: cannot read %s" % scene_dir.path_join("scene.json"))
		get_tree().quit(1)
		return
	spec = parsed
	# hands: "stump" (default) | "one" | "none" | "ball" | "mitten" | "drawn" (as painted: palm, fist, edge)
	var hs: String = str(spec.get("hands", "stump"))
	Puppet.pin_style = str(spec.get("pins", "dot"))      # "peg": the shared wooden peg on every bend; "knot"
	Puppet.glove_set = str(spec.get("gloves", "glove"))   # the shared glove set (engine/hands/<set>), "hands": "glove"
	Puppet.leather = float(spec.get("leather", 1.0))     # below 1: lit-through leather (a shadow theatre)
	Puppet.hand_style = "" if hs == "drawn" else hs
	VideoHead.loop = bool(spec.get("clip_loop", true))
	seconds = seconds_arg if seconds_arg > 0.0 else float(spec.get("seconds", 10.0))
	floor_y = SIZE.y * float(spec.get("floor", 0.86))
	var bg_image: Image = null
	if spec.has("background"):
		bg_image = Image.load_from_file(_scene_file(spec["background"]))
	if bg_image != null and spec.get("world", "") == "picture":
		world = Vector2(roundf(SIZE.y * bg_image.get_width() / bg_image.get_height()), SIZE.y)
	space = Space.new()
	space.setup(spec, world, floor_y)
	camera = Cam.new()
	camera.world = world
	camera.on = camera_on
	camera.screen = _picture() if camera_on else world
	camera.closest = float(spec.get("closest", 6.0 if spec.has("focus") else Cam.CLOSEST))
	if spec.get("camera", null) is Dictionary:
		_cam_line = spec["camera"]
	points = spec.get("points", {})
	var hz: Array = spec.get("haze", [0, 0, 0, 0])
	_haze = Color(hz[0], hz[1], hz[2], hz[3])

	# Everything is drawn on canvas layers: the background lowest, then every hero, free thing and set piece on a
	# layer of its own, sorted by depth each step (_place_layers), then the panel of the viewer.
	_back = CanvasLayer.new()
	_back.layer = -100
	add_child(_back)
	var ground := Node2D.new()
	ground.draw.connect(_draw_ground.bind(ground))
	_back.add_child(ground)
	if bg_image != null:
		var bg := Sprite2D.new()
		bg.texture = ImageTexture.create_from_image(bg_image)
		bg.centered = true
		bg.position = world * 0.5
		var k: float = maxf(world.x / bg_image.get_width(), world.y / bg_image.get_height())
		bg.scale = Vector2.ONE * k
		_back.add_child(bg)
	# FAR LAYERS behind the background (a city through a window cut in it): each at its own depth scale, so they
	# slide by parallax and blur with the focus like everything else.
	#   "backdrops": [{ "image": "city.png", "scale": 0.2, "rect": [x, y, w, h] (shares of the world) }]
	for i in spec.get("backdrops", []).size():
		_add_backdrop(spec["backdrops"][i], i)
	for pd: Dictionary in spec.get("pieces", []):
		_add_piece(pd)
	# the living background (engine/life.gd): behaviours on the pieces and on places of the picture
	life = Life.new()
	life.setup(spec.get("life", []), world, _piece_nodes, _back, self,
			func(p: Vector2) -> float: return space.ground_of(p).y)
	for l: Dictionary in life.layers:
		pieces.append({"id": "", "layer": l["layer"], "z": l["z"]})
	light = Light.new()
	light.setup_grade(self, spec, get_viewport().get_visible_rect().size)
	if spec.has("light"):
		light.setup_shadows(self, _back, world, float((spec["light"] as Dictionary).get("shadow", 0.3)))
	fx = Fx.new()
	fx.setup(self, get_viewport().get_visible_rect().size)
	if not spec.get("life", []).is_empty() or spec.has("background"):
		for w: String in life.warnings:
			print("STAGE " + w)

	# (before the heroes: their recorded voices go to the bus it makes)
	sound = Sound.new()
	sound.setup(self, spec, scene_dir)
	var layer := CanvasLayer.new()
	add_child(layer)
	var tint: Array = spec.get("tint", [1.0, 1.0, 1.0])
	_tint = Color(tint[0], tint[1], tint[2])
	for def: Dictionary in spec.get("actors", []):
		var a := _make_actor(def, layer, clip_arg)
		if a != null:
			a.puppet.modulate = Color(tint[0], tint[1], tint[2])
			actors[a.id] = a

	# things in the scene: on the floor (or held from the start)
	items = Items.new(self, floor_y, SIZE.y)
	items.world = self
	items.stage_w = world.x
	for d: Dictionary in spec.get("items", []):
		var card: String = d.get("card", d["id"])
		if FileAccess.file_exists(_scene_file(card + ".png")):
			card = _scene_file(card)
		var gz: Vector2 = _ground_place(d, false)
		items.add(d["id"], card, Vector2(gz.x, floor_y - SIZE.y * float(d.get("y", 0.0)) - 20.0), {"ground_z": gz.y})
	for i in 60:
		items.step(1.0 / 60.0)
	for a: Actor in actors.values():
		items.watch(a.motion)
		_meet_point(a)
		_partner_point(a)
	for d: Dictionary in spec.get("items", []):
		if d.has("held") and actors.has(d["held"].get("who", "")):
			var hh: String = str(d["held"].get("hand", "right"))
			if hh == "wear":
				items.wear_now(actors[d["held"]["who"]].motion, d["id"])
				continue
			items.hold_now(actors[d["held"]["who"]].motion, "both" if hh == "both" else "hand_" + hh.left(1), d["id"])

	parallax = bool(spec.get("parallax", spec.has("focus")))
	focus = Focus.new()
	focus.setup(spec, space.far_scale, self)
	if focus.on:
		focus.manage(_back)
		for bd: Dictionary in _backdrops:
			focus.manage(bd["layer"])
		for a: Actor in actors.values():
			focus.manage(a.layer)
		for pc: Dictionary in pieces:
			focus.manage(pc["layer"])
		focus.s_focus = _focus_scale()
		focus._from_s = focus.s_focus
	if parallax:
		camera.back_scale = _back_scale()
	_camera_step()
	_place_layers()
	script_lines = []
	var share: bool = spec.get("time", "seconds") == "share"
	for line: Dictionary in spec.get("script", []):
		var at_step: int = int(round(float(line.get("at", 0.0)) * (seconds if share else 1.0) * 60.0))
		line["_armed"] = at_step
		if line.has("after"):
			_waiting.append(line)
			continue
		line["_step"] = _line_step(line, at_step)
		if OS.has_environment("TIMING_DEBUG") and (line.has("phrase") or line.has("beat")):
			print("STAGE TIME %.2f s: %s (%s)" % [line["_step"] / 60.0, str(line.get("who", "")), "phrase %s" % line["phrase"] if line.has("phrase") else "beat %s" % line["beat"]])
		script_lines.append(line)
	script_lines.sort_custom(func(x: Dictionary, y: Dictionary) -> bool: return x["_step"] < y["_step"])
	if _live_port > 0:
		live = Live.new()
		if not live.setup(self, _live_port, _live_host):
			live = null


## Live: a tap or a click on a hero is an event for whoever drives the scene.
func _unhandled_input(event: InputEvent) -> void:
	if live == null:
		return
	if (event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT) or 			(event is InputEventScreenTouch and event.pressed):
		live.touch(event.position)


func _make_actor(def: Dictionary, layer: CanvasLayer, clip_arg: String) -> Actor:
	var a := Actor.new()
	a.id = def.get("id", def["puppet"])
	a.dir = def["puppet"]
	if not a.dir.is_absolute_path():
		a.dir = ProjectSettings.globalize_path("res://").path_join("../puppets").path_join(a.dir).simplify_path()
	a.height = float(def.get("height", 0.45))
	a.clip = clip_arg if not clip_arg.is_empty() else def.get("clip", "")
	if not a.clip.is_empty() and not a.clip.is_absolute_path() and not a.clip.begins_with("res://"):
		a.clip = scene_dir.path_join(a.clip)
	a.sound = bool(def.get("sound", true))
	for sp: Variant in def.get("speech", []):
		if sp is Array and (sp as Array).size() >= 2:
			a.speech.append([float(sp[0]), float(sp[1])])
	a.mouth_clip = def.get("mouth", "")
	if not a.mouth_clip.is_empty() and not a.mouth_clip.is_absolute_path() and not a.mouth_clip.begins_with("res://"):
		a.mouth_clip = scene_dir.path_join(a.mouth_clip)
	var props: Dictionary = def.get("props", {})
	for id: String in props:
		var image := Image.load_from_file(_scene_file(props[id]["image"]))
		if image != null:
			image.generate_mipmaps()
			a.prop_defs[id] = [props[id], ImageTexture.create_from_image(image), image.get_size()]
	_layer = layer
	a.layer = CanvasLayer.new()
	add_child(a.layer)
	var gz: Vector2 = _ground_place(def)
	a.z = gz.y
	a.shadow = Node2D.new()
	a.shadow.z_index = -1000
	a.shadow.draw.connect(_draw_shadow.bind(a))
	a.layer.add_child(a.shadow)
	if not _enter(a, "front", gz.x):
		return null
	if def.get("x", 0.5) is String and def["x"] in ["out_left", "out_right"]:
		# waiting beyond an edge of the stage, not drawn; a "go" brings it in
		a.out = -1.0 if def["x"] == "out_left" else 1.0
		_put_out(a)
	if a.head != null:
		# How big the face is in the picture is what the viewer came for: say it, and say when it is lost.
		var share: float = a.head.face_height * a.views["front"]["k"] / SIZE.y
		print("STAGE %s: the face is %.0f%% of the picture's height%s%s" % [a.id, share * 100.0,
				"" if share >= FACE_MIN else " - TOO SMALL, bring the actor closer (height) or the camera in",
				"" if a.head.note.is_empty() else "; " + a.head.note])
	return a


var _layer: CanvasLayer
var _tint := Color.WHITE


## The folder of a view of the hero ("" for one it does not have).
static func _view_dir(a: Actor, view: String) -> String:
	var sub: String = {"front": "", "back": "back", "side_r": "side", "side_l": "side"}.get(view, "")
	var d: String = a.dir if sub == "" else a.dir.path_join(sub)
	return d if FileAccess.file_exists(d.path_join("rig.json")) else ""


## Shows the hero in `view` with its body at `x` (stage px), standing; the face and the props go onto it.
func _enter(a: Actor, view: String, x: float) -> bool:
	if not a.views.has(view):
		var d := _view_dir(a, view)
		if d == "":
			return false
		var p := Puppet.new()
		a.layer.add_child(p)
		var bend: String = "front" if view.begins_with("side") else "out"
		if not p.load_rig(d.path_join("rig.json"), d.path_join("parts"),
				{"foot_l": {"bend": bend, "end_mode": "level"}, "foot_r": {"bend": bend, "end_mode": "level"}}):
			p.queue_free()
			return false
		p.set_rivets_visible(false)
		p.modulate = _tint
		a.views[view] = {"puppet": p, "k": SIZE.y * a.height / float(p.rig["body_height"])}
	var v: Dictionary = a.views[view]
	var p: Puppet = v["puppet"]
	var k: float = v["k"]
	var mirror: float = -1.0 if view == "side_l" else 1.0
	p.scale = Vector2.ONE
	p.position = Vector2.ZERO
	p.reset_pose()
	var sole_y := -INF
	for f: String in ["foot_l", "foot_r"]:
		sole_y = maxf(sole_y, p.point(p.rig["handles"][f]["end"], "sole").y)
	var root_x: float = p.body_position().x
	p.scale = Vector2(k * mirror, k)
	p.position = Vector2(x - root_x * k * mirror, floor_y - sole_y * k)
	p.reset_pose()
	for f: String in ["foot_l", "foot_r"]:
		p.set_target(f, p.handle_position(f))
	var phys := BodyPhysics.new()
	phys.puppet = p
	phys.floor_y = floor_y
	phys.stage_width = world.x
	phys.feet = ["foot_l", "foot_r"]
	phys.stand_here()
	phys.walls = Vector2(space.frame_x(BodyPhysics.WALL, a.z), space.frame_x(world.x - BodyPhysics.WALL, a.z))
	var mo := Motion.new()
	mo.setup(p, phys, floor_y, world)
	if a.motion != null:
		mo.adopt(a.motion)                   # the pose goes on in the new view
		a.measured = _sum(a.measured, a.motion.m)
		if items != null:
			items.rebind(a.motion, mo)       # ...and what it holds
	var old_mo: Motion = a.motion
	p.visible = true
	a.puppet = p
	a.phys = phys
	a.motion = mo
	if old_mo != null:
		_meet_point(a)
		_partner_point(a)
	a.view = view
	a.arm = mo.arm
	a.leg = mo.leg
	_dress_light(a)
	# the recorded face: moved onto this head (the clip plays on); the back of a head has no face
	var old_player: VideoStreamPlayer = a.player
	if not a.clip.is_empty() and view != "back":
		var hp: Dictionary = p.rig["parts"]["head"]
		# the recorded face is always filmed from the front: in profile it wears the hat drawn for the FRONT too
		# (a hat drawn in profile would sit on a face that looks at us)
		var front_view: Variant = a.views.get("front", null)
		if p.parts["head"].hat == null and front_view != null and front_view["puppet"] != p:
			p.parts["head"].hat = (front_view["puppet"] as Puppet).parts["head"].hat
		a.head = VideoHead.wear(p.parts["head"], hp["joint"].get("radius", 28.0), a.clip, _layer, true,
				hp.get("face", {}), float(p.rig["body_height"]), old_player,
				hp.get("board", {}) if spec.get("faces", "") == "board" else {})
		a.player = a.head.player
	elif board_preview and view != "back" and not p.parts["head"].node.has_node("face_preview"):
		var hb: Dictionary = p.rig["parts"]["head"]
		VideoHead.preview(p.parts["head"], hb["joint"].get("radius", 28.0), float(p.rig["body_height"]),
				hb.get("board", {}) if spec.get("faces", "") == "board" else {})
	# the recorded mouth: onto this view's painted face, where its mouth is drawn (the back of a head has none; the
	# clip plays on, for the voice)
	if a.mouth != null and is_instance_valid(a.mouth):
		VideoMouth.take_off(a.mouth, true)
		a.mouth = null
	if not a.mouth_clip.is_empty() and view != "back":
		var hm: Dictionary = p.rig["parts"]["head"]
		a.mouth = VideoMouth.wear(p.parts["head"], a.mouth_clip, _layer, a.sound, hm.get("mouth", {}), hm.get("face", {}),
				view.begins_with("side"), a.mouth_player)
		a.mouth_player = a.mouth.player
	# props, in the same hand
	var shown := {}
	for id: String in a.props:
		shown[id] = (a.props[id] as Sprite2D).visible
		(a.props[id] as Sprite2D).queue_free()
	a.props.clear()
	for id: String in a.prop_defs:
		var s := _make_prop(p, k, a.arm, a.prop_defs[id])
		s.visible = shown.get(id, false)
		a.props[id] = s
		if s.visible:
			mo.holding[s.get_meta("hand")] = true
			p.set_skin(s.get_meta("hand"), "fist")
	return true


## A picture held in a hand, by the point `grip` of its length; it turns with the hand.
static func _make_prop(p: Puppet, k: float, arm: float, def: Array) -> Sprite2D:
	var pd: Dictionary = def[0]
	var size_px: Vector2 = def[2]
	var hand: Object = p.parts["hand_l" if pd.get("hand", "right") == "left" else "hand_r"]
	var s := Sprite2D.new()
	s.texture = def[1]
	s.centered = false
	s.scale = Vector2.ONE * float(pd.get("length", 1.5)) * arm / k / size_px.y   # in the puppet's own px
	var hand_def: Dictionary = p.rig["parts"][hand.name]
	var at: Array = hand_def.get("grip", hand_def["joint"]["at"])
	# The picture is drawn upright, its working end at the top. In the hand that end points where the fingers
	# point: down when the arm hangs (a shovel carried), up when the hand is raised (a shovel shown). It turns
	# about the point where it is gripped, and lies behind the hand, so the closed fingers are in front of it.
	s.offset = -Vector2(size_px.x * 0.5, size_px.y * float(pd.get("grip", 0.7)))
	s.position = Vector2(at[0], at[1]) - hand.pivot
	s.rotation = deg_to_rad(180.0 + float(pd.get("angle", 0.0)))
	s.z_index = hand.z - 1
	s.set_meta("hand", hand.name)
	s.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	s.visible = false
	hand.node.add_child(s)
	return s


## Starts a turn. A flat puppet cannot be turned like a thing in space: squeezed towards its edge it shows that it
## is a card (it was like that, and it looked it). So it is done the way cut-out cartoons do it: the drawing CHANGES
## at once, and a movement hides the change: the hero dips a little, the other view comes in at the bottom of the
## dip, and it comes up out of it. ("turn_style": "squeeze" in scene.json: the old narrowing.)
func _turn(a: Actor, to: String, time := TURN_TIME) -> bool:
	var view: String = {"left": "side_l", "right": "side_r"}.get(to, to)
	if view == a.view or not a.turning.is_empty():
		return a.turning.is_empty()
	if _view_dir(a, view) == "":
		push_warning("stage: %s has no %s view" % [a.id, view])
		return false
	a.turning = {"t": 0.0, "to": view, "swapped": false, "time": time}
	var mo: Motion = a.motion
	if spec.get("turn_style", "pop") != "squeeze" and mo.chans["legs"].owner == null and not mo._seated 			and mo._gait.is_empty() and not a.phys.airborne:
		mo.play({"id": "turn_dip", "phases": [{"time": 0.08, "legs": {"drop": TURN_DIP}, "ease": "out"},
				{"time": 0.2, "legs": "rest"}]})
	return true


## The puppet's width (its x scale) changed ABOUT ITS BODY: the body stays where it is on the stage and in the
## puppet's own space. Squeezed about the picture's corner, the body slides in that space, and the springs of the
## chest and the head take it for a shove: the hero reels back after every turn.
func _set_width(a: Actor, scale_x: float) -> void:
	var p: Puppet = a.puppet
	var body_x: float = a.phys.pos.x
	var own_x: float = (body_x - p.position.x) / p.scale.x
	p.scale.x = scale_x
	p.position.x = body_x - own_x * scale_x


## One step of a turn.
func _turning(a: Actor) -> void:
	var tr := a.turning
	tr["t"] += 1.0 / 60.0
	var squeezing: bool = spec.get("turn_style", "pop") == "squeeze"
	var u: float = clampf(tr["t"] / (0.24 if squeezing else float(tr.get("time", TURN_TIME))), 0.0, 1.0)
	if u >= (0.5 if squeezing else TURN_SWAP) and not tr["swapped"]:
		var old: Puppet = a.puppet
		var x: float = old.body_position().x
		if a.head != null:
			VideoHead.take_off(a.head, old.parts["head"], true)
			a.head = null
		old.visible = false
		_enter(a, tr["to"], x)
		tr["swapped"] = true
	# narrows and widens again, the view changing at the narrowest. NOT down to an edge: a flat puppet squeezed to
	# a sliver shows that it is paper; at a little over half its width it reads as a three-quarter turn
	var squeeze: float = TURN_NARROW + (1.0 - TURN_NARROW) * absf(cos(PI * u)) if squeezing 			else 1.0 - TURN_BREATH * sin(PI * u)
	var v: Dictionary = a.views[a.view]
	_set_width(a, v["k"] * squeeze * (-1.0 if a.view == "side_l" else 1.0))
	if u >= 1.0:
		_set_width(a, v["k"] * (-1.0 if a.view == "side_l" else 1.0))
		a.turning = {}
		var queued := a.after
		a.after = []
		for line: Dictionary in queued:
			_command(line)


## An old-style hand place (PLACES) as a little action: the hand goes there and lives there until told otherwise.
static func _place_action(place: String, side: String) -> Dictionary:
	var pl: Array = PLACES.get(place, PLACES["down"])
	var hz: float = float(pl[4]) * 60.0 / TAU
	var arm := {"at": [pl[0], pl[1]]}
	var live := {}
	if pl[2] != 0.0 or pl[3] != 0.0:
		live["at"] = {"base": [pl[0], pl[1]], "amp": [pl[2], pl[3]], "rate": hz}
	if pl[5] != 0.0:
		live["wrist"] = {"base": 0, "amp": pl[5], "rate": hz}
	if place in ["chest", "rub"]:
		arm["contact"] = true
		live["contact"] = true
	var key := "arm_l" if side == "left" else "arm_r"
	var phases: Array = [{"time": 0.5, key: arm}]
	if not live.is_empty():
		phases.append({"time": 1.0, "loop": true, key: live})
	return {"id": "place_" + place, "phases": phases}


func _command(line: Dictionary) -> void:
	if line.has("focus") or line.has("aperture"):
		focus.command(line, focus.s_focus)
		if not line.has("who") and not line.has("camera"):
			return
	if line.has("camera"):
		_camera_command(line)
		if not line.has("who"):
			return
	if line.has("grade"):
		light.change(line["grade"], float(line.get("time", 1.0)))
		if not line.has("who"):
			return
	if line.has("sound") or line.has("music"):
		sound.command(line)
		if not line.has("who"):
			return
	var over := {}                                 # titles and the like: not about any one hero
	for k: String in ["subtitle", "title", "flash", "confetti"]:
		if line.has(k):
			over[k] = line[k]
	if not over.is_empty():
		if line.has("for"):
			over["for"] = line["for"]
		fx.command(over, step_no, _head_screen)
		if not line.has("who"):
			return
	if line.get("who", "") == "all":              # the same command for everyone on the stage
		for id: String in actors:
			var each := line.duplicate()
			each["who"] = id
			_command(each)
		return
	var a: Actor = actors.get(line.get("who", ""), null)
	if a == null and not actors.is_empty():
		a = actors.values()[0]
	if a == null:
		return
	if not a.turning.is_empty():                 # mid-turn: it happens once the turn is over
		a.after.append(line)
		return
	if line.has("_event"):
		_events.append([step_no, a.id, str(line["_event"])])
		return
	if line.has("label"):
		_labels[str(line["label"])] = [a.id, _started(line), step_no]
		if OS.has_environment("TIMING_DEBUG"):
			print("STAGE LABEL %.2f %s %s view=%s turning=%s going=%s" % [step_no / 60.0, line["label"], _started(line), a.view, str(a.turning), str(a.going.get("stage", ""))])
	if line.has("say"):
		_events.append([step_no + int(float(line.get("for", 2.5)) * 60.0), a.id, "say"])
		_talk.append([a.id, step_no, step_no + int(float(line.get("for", 2.5)) * 60.0)])
	if line.has("say") or line.has("stars"):
		var said := {"who": a.id}
		for k: String in ["say", "stars", "for"]:
			if line.has(k):
				said[k] = line[k]
		fx.command(said, step_no, _head_screen)
	if line.has("turn"):
		var to_view: String = {"left": "side_l", "right": "side_r"}.get(str(line["turn"]), str(line["turn"]))
		if to_view == a.view:
			_events.append([step_no, a.id, "turn"])     # (turned that way already: done at once, for "after")
		_turn(a, line["turn"], float(line.get("_time", TURN_TIME)))
		var rest := line.duplicate()
		rest.erase("turn")
		rest.erase("_time")
		if not rest.has("do"):
			rest.erase("label")       # (the label is the turn's: what is left of the line does not take it over)
		if rest.size() > 1 or (rest.size() == 1 and not rest.has("who")):
			a.after.append(rest)
		return
	if line.has("spin"):
		# a spin ("юла"): round and round through every view the hero has (front, profile, back, profile...),
		# each drawing put in at once, as in any turn; "spin": how many times round, "time": seconds a round
		var order: Array = ["front", "side_r", "back", "side_l"].filter(func(v: String) -> bool: return _view_dir(a, v) != "")
		if order.size() < 2:
			push_warning("stage: %s has no other view to spin through" % a.id)
			_events.append([step_no, a.id, "spin"])
			return
		var per: float = float(line.get("time", SPIN_TIME)) / float(order.size())
		sound.play("spin", -4.0)
		var at: int = maxi(order.find(a.view), 0)
		var first := true
		for q in range(1, int(line.get("spin", 1)) * order.size() + 1):
			var v: String = order[(at + q) % order.size()]
			if first:
				_turn(a, v, per)
				first = false
			else:
				a.after.append({"who": a.id, "turn": v, "_time": per})
		a.after.append({"who": a.id, "_event": "spin"})      # (the last turn is over: the spin is, for "after")
		return
	if line.has("go"):
		# where to: across (x) and into the depth (z), in this hero's frame as it stands now
		var to: Vector2 = _go_target(a, line)
		var dx: float = to.x - a.puppet.body_position().x
		var dz: float = to.y - a.z
		if OS.has_environment("STAGE_DEBUG"):
			print("GO %d %s dx=%.0f dz=%.0f view=%s going=%s turning=%s" % [step_no, a.id, dx, dz, a.view, str(a.going.get("stage", "")), str(a.turning)])
		var then: String = line.get("then", "front")
		if line["go"] is String and line["go"] in ["out_left", "out_right"]:
			a.leaving = -1.0 if line["go"] == "out_left" else 1.0
			then = "keep"                          # (it walks out as it walks, in profile)
		elif a.out != 0.0:
			a.out = 0.0                            # coming in from beyond the edge: drawn again from now on
			a.layer.visible = true
			a.entering = true                      # (the sides of the stage must not snap its body in ahead of its feet)
		if line["go"] is String and actors.has(line["go"]) and not line.has("then"):
			# (up to a hero: it stands facing it, ready to fight)
			then = "right" if _from(actors[line["go"]], a, actors[line["go"]].puppet.body_position()).x > a.puppet.body_position().x else "left"
		var pt: Dictionary = points.get(line["go"], {}) if line["go"] is String else {}
		if pt.has("face") and not line.has("then"):
			then = pt["face"]                       # a point can say which way to stand there
		a.going = {"stage": "turn", "dx": dx, "dz": dz, "z0": a.z, "z1": to.y, "then": then, "speed": line.get("speed", null),
			"next": line.get("_next", {}), "style": line.get("style", "walk")}
		if Vector2(dx, dz).length() < 0.1 * a.leg:
			a.going = {}
			a.z = to.y
			_events.append([step_no, a.id, "go"])           # (there already: arrived at once, for "after")
			if then != "keep" and then != a.view and then in ["left", "right", "back"]:
				_turn(a, then)
			if not line.get("_next", {}).is_empty():
				_command(line["_next"])
		elif absf(dx) < 0.6 * absf(dz) or spec.get("walk", "") == "front" or line.get("frontal", false):
			# mostly into the depth (or out of it): it goes with its back to us, or facing us, stepping on the spot.
			# "walk": "front" (the camera rules, docs/shooting.md): every walk faces us, a diagonal too
			var view: String = "back" if dz > 0.0 and _view_dir(a, "back") != "" else "front"
			a.going["stage"] = "walk"
			if view != a.view:
				_turn(a, view)
		elif _view_dir(a, "side_r") != "":
			_turn(a, "right" if dx > 0.0 else "left")
		else:
			a.going["stage"] = "walk"            # no side view: it steps sideways as it is
		return
	if _item_command(a, line):
		return
	if line.has("sit") and line["sit"] is String:
		# furniture: a point with a "seat" (its height over the ground there, share of the stage height). The hero goes
		# there, turns the way the point says, sits on it and stays ("for": seconds; else until "stand")
		var seat: String = line["sit"]
		if not points.has(seat) or not points[seat].has("seat"):
			push_warning("stage: no seat '%s'" % seat)
			return
		var sit := {"who": a.id, "do": "sit", "_seat": seat, "duration": float(line.get("for", 1e5))}
		_command({"who": a.id, "go": seat, "_next": sit})
		return
	if line.get("stand", false):
		var run: Variant = a.playing.get("sit", a.playing.get("sit_floor", null))
		if run != null and not run.done:
			if run.phases[run.i].get("loop", false):
				run.length = run.t                   # the sitting is over: it gets up the way the action does
			else:
				a.motion.release(run)
		return
	var act0: Variant = line.get("do", null)
	if act0 is String and actions().has(act0) and actions()[act0].has("pair") and line.has("with"):
		_pair_command(a, line)
		return
	# a blow at another hero ("to": its id): first up to where it lands, facing it, if it is not there already
	if act0 is String and actions().has(act0) and actions()[act0].get("group", "") == "fight" and actors.has(line.get("to", "")) 			and not line.get("_near", false):
		var b: Actor = actors[line["to"]]
		var me: Vector2 = a.puppet.body_position()
		var them: Vector2 = _from(b, a, b.puppet.body_position())
		var facing_them: bool = a.view == ("side_r" if them.x > me.x else "side_l")
		if absf(absf(them.x - me.x) - _strike_gap(a, b)) > 0.15 * a.arm or absf(b.z - a.z) > 0.05 * a.leg or not facing_them:
			var then := line.duplicate()
			then["_near"] = true
			_command({"who": a.id, "go": line["to"], "_next": then})
			return
	if act0 is String and actions().has(act0):
		var need_view: String = actions()[act0].get("view", "")
		if need_view == "side" and not a.view.begins_with("side") and _view_dir(a, "side_r") != "":
			var back_to: String = a.view
			_turn(a, "left" if line.get("facing", "right") == "left" else "right")
			var then := line.duplicate()
			then["_back_to"] = back_to             # turned only for this action: turned back after it
			a.after.append(then)
			return
	var mo := a.motion
	for key: String in ["hands", "left", "right"]:
		if line.has(key):
			for side: String in (["left", "right"] if key == "hands" else [key]):
				mo.play(_place_action(line[key], side))
	var body := {}
	if line.has("lean"):
		body["lean"] = float(line["lean"])
	if line.has("bow"):
		body["chest"] = float(line["bow"])
	if not body.is_empty():
		mo.play({"id": "lean", "phases": [{"time": 0.6, "body": body}]})
	if line.has("head") and not (line["head"] is String):
		mo.play({"id": "head", "phases": [{"time": 0.4, "head": float(line["head"])}]})
	var act: Variant = line.get("do", null)
	if act is String:
		var params := {}
		for k: String in ["side", "energy", "speed", "duration", "height"]:
			if line.has(k):
				params[k] = line[k]
		if actions().has(act):
			for k: String in actions()[act].get("params", {}):
				if line.has(k) and k != "item":
					params[k] = line[k]          # (the action's own params: "dist" of a jump forward...)
		var bpm: float = _music_beat().x
		if bpm > 0.0 and actions().has(act) and actions()[act].has("beat_rate") and not line.has("speed"):
			# a dance at the music's tempo: its step on the beat (or on every other one, or twice a beat)
			var kb: float = bpm / 60.0 / float(actions()[act]["beat_rate"])
			while kb > 1.45:
				kb *= 0.5
			while kb < 0.72:
				kb *= 2.0
			params["speed"] = kb
		if line.has("_seat"):
			# the seat's height on the screen, in this hero's leg lengths where it stands
			params["height"] = float(points[line["_seat"]]["seat"]) * SIZE.y / space.scale_at(a.z) / a.leg
			if OS.has_environment("STAGE_DEBUG"):
				print("SEAT %s height=%.2f legs, hem=%.2f legs, leg=%.0f" % [a.id, params["height"], (floor_y - a.motion._rest_low.get("pelvis", floor_y)) / a.leg, a.leg])
		# an action about a thing ("item"): the one in the hero's hands, unless the line names another
		if actions().has(act) and actions()[act].get("params", {}).has("item"):
			var held: String = ""
			for k2: String in items.items:
				if items.items[k2].holder == mo:
					held = k2
			if line.has("item"):
				params["item"] = "@" + str(line["item"])
			elif held != "":
				params["item"] = "@" + held
		match act:
			"stamp_left", "stamp_right":
				params["side"] = act.trim_prefix("stamp_")
				act = "stamp"
		if actions().has(act):
			a.playing[act] = mo.play(actions()[act], params)
			if act == "get_hit":
				fx.stars(a.id, 1.4, step_no, _head_screen)        # (stars round the head after a blow)
			if line.has("_back_to"):
				a.back_to = [a.playing[act], line["_back_to"]]
			elif not a.back_to.is_empty() and actions()[act].get("view", "") != "":
				a.back_to[0] = a.playing[act]       # still in the view it was turned to: back after THIS one
		else:
			push_warning("stage: no action '%s'" % act)
	var stop: Variant = line.get("stop", null)
	if stop is String:
		for id: String in a.playing.keys():
			if stop == "all" or stop == id:
				mo.release(a.playing[id])
				a.playing.erase(id)
	# a hand that holds something closes round it; empty again, it goes back to choosing its own drawing
	if line.has("show") and a.props.has(line["show"]):
		var prop: Sprite2D = a.props[line["show"]]
		prop.visible = true
		mo.holding[prop.get_meta("hand")] = true
		a.puppet.set_skin(prop.get_meta("hand"), "fist")
	if line.has("hide") and a.props.has(line["hide"]):
		var prop: Sprite2D = a.props[line["hide"]]
		prop.visible = false
		mo.holding.erase(prop.get_meta("hand"))
		a.puppet.release_skin(prop.get_meta("hand"))


func _physics_process(_delta: float) -> void:
	step_no += 1
	while _next < script_lines.size() and int(script_lines[_next]["_step"]) <= step_no:
		_command(script_lines[_next])
		_next += 1
	if not _due.is_empty():
		var later: Array = []
		for d: Array in _due:
			if int(d[0]) <= step_no:
				if OS.has_environment("TIMING_DEBUG"):
					print("STAGE TIME %.2f s: %s (after %s)" % [step_no / 60.0, str(d[1].get("who", "")), str(d[1]["after"])])
				_command(d[1])
			else:
				later.append(d)
		_due = later
	for a: Actor in actors.values():
		if not a.turning.is_empty():
			_turning(a)
		_going(a)
		# turned only for an action, it turns back once it is over, and only once it is ON ITS FEET: a hero that
		# fell or sat down stays in the view it is lying or sitting in (turned to the front lying on its back, the
		# front picture lay on its side) until something gets it up
		if not a.back_to.is_empty() and (a.back_to[0] as Object).done and a.turning.is_empty() and _upright(a):
			var v: String = a.back_to[1]
			a.back_to = []
			_turn(a, v)
		a.motion.measuring = a.turning.is_empty()
		a.motion.step()
		_mouth_step(a)
	items.step(1.0 / 60.0)
	life.step(step_no)
	light.step(step_no)
	var heard: Array = []
	for a: Actor in actors.values():
		_light_step(a)
		if a.out == 0.0:
			heard.append([a.motion, a.phys, space.scale_at(a.z)])
	sound.step(heard)
	_log_events()
	if live != null:
		live.step()
	if checking:
		_check_step()
	fx.step(step_no)
	if step_no % 30 == 0:
		# nothing living in front of the heroes covers a face (said once per element and hero)
		for fb: Array in life.front_boxes():
			for a: Actor in actors.values():
				var key: String = "%s/%s" % [fb[0], a.id]
				if not _covered.has(key) and a.out == 0.0 and (fb[1] as Rect2).intersects(_head_box(a)):   # (both in the world)
					_covered[key] = true
					print("STAGE life: %s covers the face of %s at %.1f s" % [fb[0], a.id, step_no / 60.0])
	_camera_step()
	_place_layers()
	if OS.has_environment("STAGE_DEBUG"):
		for a: Actor in actors.values():
			var mo: Motion = a.motion
			var cl: Variant = mo.cloth
			var ang := 0.0
			if cl != null:
				for i in range(1, cl.pts.size()):
					var d: Vector2 = cl.pts[i] - cl.pts[i - 1]
					ang = maxf(ang, absf(rad_to_deg(atan2(d.x, d.y))))
			if cl != null and OS.get_environment("STAGE_DEBUG") == "links":
				var ls := []
				for i in range(1, cl.pts.size()):
					var d2: Vector2 = cl.pts[i] - cl.pts[i - 1]
					ls.append("%.0f" % rad_to_deg(atan2(d2.x, d2.y)))
				var sk: Variant = mo.puppet.parts["skirt"]
				print("LINKS %d part=%.0f links=%s pts0=%s" % [step_no, rad_to_deg(sk.xf.get_rotation()), " ".join(ls), str(cl.pts[0].round())])
			if step_no % 30 == 0:
				print("POS %d x=%.0f view=%s facing=%.0f scale=%.2f skin=%s walk_w=%.2f fists=%s runs=%s" % [step_no, a.puppet.body_position().x, a.view, mo.facing, a.puppet.scale.x,
					a.puppet.parts["hand_r"].skin + " at=" + str(mo.chans["arm_r"].now["at"]) + " own=" + (mo.chans["arm_r"].owner.id if mo.chans["arm_r"].owner else "-"), mo._walk_w, str(mo._gait_look.get("fists")), str(mo.runs.map(func(r): return r.id + ":" + str(r.i)))])
			print("DBG %d %s view=%s lean=%.1f fix=%.1f lift=%.1f squat=%.1f turning=%s cloth_ang=%.0f sq=%.2f" % [step_no, a.id, a.view,
				rad_to_deg(a.puppet.body_lean), mo._lean_fix, mo._lift_fix, mo.phys.squat, str(not a.turning.is_empty()), ang, cl.squash if cl != null else 1.0])
	if step_no == int(seconds * 60.0):
		for a: Actor in actors.values():
			var m: Dictionary = _sum(a.measured, a.motion.m)
			print("STAGE %s: %d steps; longest run of a joint on the wrong side %d steps; hands went %.1f arm lengths where %.1f were needed (%.2f times); feet slid %.3f, under the floor %.3f leg lengths; face covered %.1f s" %
					[a.id, int(m["steps"]), int(m["wrong_run"]), m["travel"], m["needed"], m["travel"] / maxf(m["needed"], 0.01),
					m["slide"], m["floor"], m["face"]])


## SPEECH WITH NO SOUND, for the eye (a line not recorded yet: the kit's local player): in each phrase of the
## line the painted mouth is open and shut for the step counts of TALK, in a loop (even places open), as the
## lab's demo did; between the phrases and after them it is shut. A head with no "open" drawing stays as it is.
const TALK: Array[int] = [6, 4, 7, 5, 5, 4, 9, 16, 6, 5, 6, 4, 8, 5, 10, 26]   # steps open, shut, open, ...
static var _talk_total := 0


func _speaking(a: Actor, t: float) -> bool:
	for sp: Array in a.speech:
		if t >= float(sp[0]) and t < float(sp[1]):
			return true
	return false


func _mouth_step(a: Actor) -> void:
	if a.speech.is_empty() or board_preview or a.puppet == null or not a.puppet.parts.has("head"):
		return              # (--board-preview: a recorded face will talk there, not the painted mouth)
	if _talk_total == 0:
		for n: int in TALK:
			_talk_total += n
	var t: float = step_no / 60.0
	var open := false
	if a.view != "back":
		for sp: Array in a.speech:
			if t >= float(sp[0]) and t < float(sp[1]):
				var k: int = (step_no - int(round(float(sp[0]) * 60.0))) % _talk_total
				for i in TALK.size():
					if k < TALK[i]:
						open = i % 2 == 0
						break
					k -= TALK[i]
				break
	var want := "open" if open else ""
	var head: Variant = a.puppet.parts["head"]
	if head.skin != want and head.skins.has(want):
		a.puppet.set_skin("head", want, false)


## Two measurements together: counts and lengths add up, worst cases stay the worst.
static func _sum(x: Dictionary, y: Dictionary) -> Dictionary:
	if x.is_empty():
		return y.duplicate()
	var out := x.duplicate()
	for k: String in y:
		if k in ["steps", "wrong", "travel", "needed", "airborne"]:
			out[k] = float(out.get(k, 0.0)) + float(y[k])
		elif y[k] is float or y[k] is int:
			out[k] = maxf(float(out.get(k, 0.0)), float(y[k]))
	return out


## Things: "take": item id (walks up to it first if it is out of reach), "put": true, "throw": true or a hero's id
## (at that hero), "catch": true, "give": a hero's id (the two hands meet half way, the thing goes over).
## "side" picks the hand; by default the one nearer the thing, or the one holding it.
## The picture's size: the window's, or (checked unseen, there is no window) the film's, by the scene's "format".
func _picture() -> Vector2:
	if checking:
		return {"1:1": Vector2(720, 720), "16:9": Vector2(1280, 720)}.get(str(spec.get("format", "9:16")), Vector2(720, 1280))
	return get_viewport().get_visible_rect().size


## --check: is every hero that talks now (a bubble, or its recorded voice in a phrase) seen, facing us, big enough?
func _check_step() -> void:
	var t: float = step_no / 60.0
	for a: Actor in actors.values():
		var talking := false
		var voiced := false
		for tk: Array in _talk:
			if tk[0] == a.id and step_no >= int(tk[1]) and step_no < int(tk[2]):
				talking = true
		if a.clip != "" or a.mouth_clip != "":
			for ph: Array in _phrases(a.id):
				if t >= float(ph[0]) and t < float(ph[1]):
					talking = true
					voiced = true
		elif _speaking(a, t):
			talking = true              # (a line with no recording: it must be seen saying it)
		if not talking:
			continue
		var head: Variant = _head_screen(a.id)
		var pic: Vector2 = camera.screen
		if head == null or not Rect2(Vector2.ZERO, pic).grow(-4.0).has_point(head + Vector2(0.0, 0.08 * pic.y)):
			_problem("offscreen", a.id, t)
		elif voiced and a.view == "back":
			_problem("back", a.id, t)
		elif voiced and a.head != null and a.views.has(a.view):
			var share: float = a.head.face_height * float(a.views[a.view]["k"]) * space.scale_at(a.z) * camera.zoom / pic.y
			if share < FACE_MIN:
				_problem("small_face", a.id, t)
	if step_no >= int(seconds * 60.0):
		for line: Dictionary in _waiting:              # waited for something that never happened
			_problem("never", str(line.get("who", "")) + " " + str(line["after"]), t)
		var out := {}
		for key: String in _problems:
			out[key] = _problems[key]
		print("CHECK " + JSON.stringify({"seconds": seconds, "problems": out}))
		checking = false
		get_tree().quit()


func _problem(kind: String, who: String, t: float) -> void:
	var key: String = kind + "|" + who
	var spans: Array = _problems.get(key, [])
	if not spans.is_empty() and t - float(spans[-1][1]) < 0.1:
		spans[-1][1] = snappedf(t, 0.01)
	else:
		spans.append([snappedf(t, 0.01), snappedf(t, 0.01)])
	_problems[key] = spans


## When a line happens (see the header): its step, for "at", "phrase" and "beat".
func _line_step(line: Dictionary, at_step: int) -> int:
	var delay: int = int(round(float(line.get("delay", 0.0)) * 60.0))
	if line.has("phrase"):
		var ph: Array = _phrases(str(line.get("voice", line.get("who", ""))))
		var n: int = int(line["phrase"])
		if n >= 1 and n <= ph.size():
			return int(round(float(ph[n - 1][1 if line.get("end", false) else 0]) * 60.0)) + delay
		push_warning("stage: no phrase %d of %s's voice (%d found)" % [n, str(line.get("voice", line.get("who", "?"))), ph.size()])
	if line.has("beat"):
		var b: Vector2 = _music_beat()
		if b.x > 0.0:
			return int(round((b.y + (float(line["beat"]) - 1.0) * 60.0 / b.x) * 60.0)) + delay
		push_warning("stage: a line on a beat, and the music has no bpm (tools/bpm.py)")
	return at_step + delay


## The music's tempo: (beats a minute, seconds to the first beat); (0, 0) if it has none.
func _music_beat() -> Vector2:
	var m: Variant = spec.get("music", null)
	if m is Dictionary and (m as Dictionary).has("bpm"):
		return Vector2(float(m["bpm"]), float(m.get("offset", 0.0)))
	return Vector2.ZERO


## The phrases of a hero's recorded voice (tools/phrases.py), or of the first hero that has one. A hero with no
## recording that says a line ("speech") has the phrases of that line.
func _phrases(who: String) -> Array:
	if actors.has(who):
		var w: Actor = actors[who]
		if w.clip == "" and w.mouth_clip == "" and not w.speech.is_empty():
			return w.speech
	var order: Array = []
	if actors.has(who):
		order.append(actors[who])
	order.append_array(actors.values())
	var clip := ""
	for b: Actor in order:
		if b.clip != "" or b.mouth_clip != "":
			clip = b.clip if b.clip != "" else b.mouth_clip
			break
	if clip == "":
		return []
	if not _phrase_cache.has(clip):
		var f: String = clip + ".phrases.json"
		var got: Variant = JSON.parse_string(FileAccess.get_file_as_string(f)) if FileAccess.file_exists(f) else null
		_phrase_cache[clip] = got if got is Array else []
		if got == null:
			push_warning("stage: no phrases for %s (tools/phrases.py)" % clip)
	return _phrase_cache[clip]


## What a line starts, as it will be logged when it is over ("after").
static func _started(line: Dictionary) -> String:
	if line.get("do", null) is String:
		return line["do"]
	for k: String in ["go", "sit", "take", "put", "throw", "turn", "play", "say", "spin"]:
		if line.has(k):
			return k
	return ""


## What every hero finished this step (for "after"), and the waiting lines whose moment came.
func _log_events() -> void:
	for a: Actor in actors.values():
		for act: String in a.playing:
			var run: Variant = a.playing[act]
			if run is Object and run.done and not _logged.has(run):
				_logged[run] = true
				_events.append([step_no, a.id, "play" if act == "_music" else act])
		var was: Array = _was.get(a.id, [false, false])
		var now := [not a.going.is_empty(), not a.turning.is_empty()]
		if was[0] and not now[0]:
			_events.append([step_no, a.id, "go"])
		if was[1] and not now[1]:
			_events.append([step_no, a.id, "turn"])
		_was[a.id] = now
	if OS.has_environment("TIMING_DEBUG"):
		for e: Array in _events:
			if int(e[0]) == step_no:
				print("STAGE EVENT %.2f %s %s" % [step_no / 60.0, e[1], e[2]])
	if _waiting.is_empty():
		return
	var still: Array = []
	for line: Dictionary in _waiting:
		var at: int = _after_step(line)
		if at < 0:
			still.append(line)
		else:
			_due.append([at + int(round(float(line.get("delay", 0.0)) * 60.0)), line])
	_waiting = still


## The step at which what a waiting line waits for was finished, or -1 (not yet).
func _after_step(line: Dictionary) -> int:
	var what: String = str(line["after"])
	var who: Array = []
	var since: int = int(line.get("_armed", 0))
	if what.begins_with("#"):
		var lb: Variant = _labels.get(what.substr(1), null)
		if lb == null:
			return -1
		who = [lb[0]]
		what = lb[1]
		since = int(lb[2])
	else:
		var w: String = str(line.get("of", line.get("who", "")))
		who = actors.keys() if w == "all" else [w]
	var last := -1
	for id: String in who:
		var found := -1
		for e: Array in _events:
			if e[1] == id and e[2] == what and int(e[0]) >= since and int(e[0]) <= step_no:
				found = int(e[0])
				break
		if found < 0:
			return -1
		last = maxi(last, found)
	return last


## "play": an INSTRUMENT (a card in engine/items or the scene's folder: guitar, balalaika, drum, accordion, bass,
## pipe): the hero gets it (on its strap, at its mouth, in both hands, standing beside it; a drum with its sticks),
## turns to the front, and plays it ("for": seconds; without it, until "play": "off", which puts it away).
func _play_command(a: Actor, line: Dictionary) -> void:
	var mo := a.motion
	var what: String = str(line["play"])
	if what in ["off", "stop", ""]:
		var run: Variant = a.playing.get("_music", null)
		if run != null and not run.done:
			mo.release(run)
		for id: String in a.instruments:
			items.remove(id)
		a.instruments.clear()
		return
	if a.view != "front" and _view_dir(a, "front") != "":
		_turn(a, "front")                        # (played facing us)
		a.after.append(line)
		return
	var card: String = _scene_file(what) if FileAccess.file_exists(_scene_file(what + ".png")) else what
	var id: String = "%s_%s" % [what, a.id]
	if not items.items.has(id):
		for old: String in a.instruments:
			items.remove(old)
		a.instruments.clear()
		var it: Variant = items.add(id, card, a.puppet.body_position(), {"ground_z": a.z})
		var hold: Variant = it.def.get("hold", "hand")
		if hold is String and hold == "wear":
			items.wear_now(mo, id)
		else:
			items.hold_now(mo, "both" if hold is String and hold == "both" else "hand_r", id)
		a.instruments.append(id)
		for w: Dictionary in it.def.get("with", []):
			var id2: String = "%s_%s_%s" % [w["card"], w.get("hand", "right"), a.id]
			var extra := {"ground_z": a.z}
			if w.has("hold"):
				extra["hold"] = w["hold"]          # (held the way this instrument wants: drumsticks slanted down at it)
			items.add(id2, str(w["card"]), a.puppet.body_position(), extra)
			items.hold_now(mo, "hand_" + str(w.get("hand", "right")).left(1), id2)
			a.instruments.append(id2)
	var act: String = str(items.items[id].def.get("play", ""))
	if not actions().has(act):
		push_warning("stage: no action to play '%s'" % what)
		return
	var params := {"item": "@" + id, "duration": float(line.get("for", 1e5))}     # (no "for": until "play": "off")
	for k: String in ["energy", "speed"]:
		if line.has(k):
			params[k] = line[k]
	var how: Dictionary = actions()[act]
	if mo._seated or (mo.chans["legs"].owner != null and not mo.chans["legs"].owner.done and mo.chans["legs"].owner.id.begins_with("sit")):
		# played sitting: the legs stay as they sit (the bob of a standing player would get it up)
		how = how.duplicate(true)
		for ph: Dictionary in how.get("phases", []):
			ph.erase("legs")
	a.playing["_music"] = mo.play(how, params)


func _item_command(a: Actor, line: Dictionary) -> bool:
	var mo := a.motion
	if line.has("play"):
		_play_command(a, line)
		return true
	if line.has("take"):
		var id: String = line["take"]
		if not items.items.has(id):
			push_warning("stage: no item '%s'" % id)
			return true
		var it: Variant = items.items[id]
		if not line.get("_near", false) and absf(it.z - a.z) > 0.05 * a.leg and it.holder == null:
			# it lies deeper in (or nearer): first to its depth, beside it
			var there := line.duplicate()
			var on_ground: Vector2 = space.transform_at(it.z) * it.pos
			var me_ground: Vector2 = space.transform_at(a.z) * a.puppet.body_position()
			var off: float = 0.55 * a.arm * space.scale_at(it.z) * (1.0 if me_ground.x < on_ground.x else -1.0)
			_command({"who": a.id, "go": (on_ground.x - off) / world.x, "depth": it.z / maxf(space.depth, 1.0), "_next": there})
			return true
		var body: Vector2 = a.puppet.body_position()
		# (lying on the floor: its lowest point there. Its grip may be high on it: a crate is taken by its middle)
		var on_floor: bool = it.holder == null and items._lowest(it) > floor_y - 0.1 * a.leg
		if OS.has_environment("STAGE_DEBUG"):
			print("TAKE %d %s %s low=%.0f floor=%.0f leg=%.0f view=%s profile=%s" % [step_no, a.id, id, items._lowest(it), floor_y, a.leg, a.view, str(_low_in_profile(a))])
		var both: bool = it.def.get("hold", "") is String and it.def.get("hold", "") == "both"
		var centre_x: float = items._local_to_world(it, Vector2(0.5, 0.5)).x
		# A thing on the FLOOR is taken in profile by a hero that has one: seen from the front a body cannot bend
		# down towards us, and a short-armed one does not reach the floor at all. It turns to the thing, takes it,
		# and turns back (how cut-out animation does it).
		var toward: String = "right" if (centre_x if both else it.pos.x) > body.x else "left"
		if on_floor and _view_dir(a, "side_r") != "" and a.view != {"right": "side_r", "left": "side_l"}[toward]:
			# (in profile already but facing away from it: it turns round to it, and stays in profile after)
			var was: String = a.view
			# (a turn back still waiting from the action before - put down in profile - is this one's turn back now:
			# else it fired in the middle of this one and the thing was lifted seen from the front)
			if not a.back_to.is_empty():
				was = a.back_to[1]
				a.back_to = []
			_turn(a, toward)
			var again := line.duplicate()
			if was in ["front", "back"]:
				again["_back_to"] = line.get("_back_to", was)
			a.after.append(again)
			return true
		var side: String = line.get("side", "")
		if side == "":
			side = "right" if signf(it.pos.x - body.x) == mo._sign("arm_r") else "left"
		# a thing on the floor: where the shoulder will be over it as the body bends down (motion.floor_reach_x);
		# on a table, an arm's reach and a half aside
		var off: float = mo.floor_reach_x("arm_" + side.left(1)) if on_floor else 0.55 * a.arm
		var want_x: float = it.pos.x - off * mo._sign("arm_" + side.left(1))
		if a.view != "front":
			want_x = it.pos.x - off * signf(it.pos.x - body.x)
		if both:
			want_x = centre_x                  # both hands: right in front of it...
			if a.view.begins_with("side"):     # ...in profile: behind it, so that it is carried in front of the belly
				want_x = centre_x - items.carry_out(mo, it) * signf(centre_x - body.x)
		if absf(want_x - body.x) > 0.3 * a.arm and not line.get("_near", false):
			var then := line.duplicate()
			then["_near"] = true
			then.erase("side")                     # (chosen again where it stands)
			var go := {"who": a.id, "go": (space.vx + (want_x - space.vx) * space.scale_at(a.z)) / world.x, "_next": then}
			if a.view.begins_with("side"):
				go["then"] = "keep"                # (turned to it already: it stays turned that way)
			_command(go)
			return true
		var heavy: bool = both
		a.playing["take"] = mo.play(actions()["lift" if heavy else "take"], {"side": side, "item": "@" + id})
		if line.has("_back_to"):
			a.back_to = [a.playing["take"], line["_back_to"]]
		return true
	var hand: String = items.held_by(mo)
	var side_held: String = line.get("side", "left" if hand == "hand_l" else "right")
	if line.has("put"):
		if hand != "" and _low_in_profile(a) and a.back_to.is_empty():
			# (put down on the floor in profile too, the way the hand holding it is)
			_turn(a, "right" if mo._sign("arm_" + side_held.left(1)) > 0.0 else "left")
			var again := line.duplicate()
			again["_back_to"] = line.get("_back_to", a.view)
			a.after.append(again)
			return true
		if hand != "":
			a.playing["put"] = mo.play(actions()["put"], {"side": side_held})
			if line.has("_back_to"):
				a.back_to = [a.playing["put"], line["_back_to"]]
		return true
	if line.has("throw"):
		if hand != "":
			var at: Variant = line["throw"]
			if at is String and actors.has(at):
				# at the hand the other one catches with (the one towards the thrower, held up as "catch" holds it)
				var other: Actor = actors[at]
				var ch: String = _facing_arm(other, _from(a, other, a.puppet.body_position()).x)
				mo.throw_at = _from(other, a, other.motion._shoulder_at(ch, other.puppet.body_position()) + Vector2(0.45 * other.motion._sign(ch), -0.2) * other.arm)
			a.playing["throw"] = mo.play(actions()["throw"], {"side": side_held})
		return true
	if line.has("catch"):
		var from_x: float = a.puppet.body_position().x + 1.0
		for o: Actor in actors.values():
			if o != a and items.held_by(o.motion) != "":
				from_x = _from(o, a, o.puppet.body_position()).x
		var side: String = line.get("side", "right" if _facing_arm(a, from_x) == "arm_r" else "left")
		a.playing["catch"] = mo.play(actions()["catch"], {"side": side})
		return true
	if line.has("give"):
		var to: Actor = actors.get(line["give"], null)
		if to == null or hand == "":
			return true
		var id := ""
		for k: String in items.items:
			if items.items[k].holder == mo:
				id = k
		a.playing["give"] = mo.play(actions()["give"], {"side": side_held, "to": "@meet"})
		var tb: Vector2 = to.puppet.body_position()
		var their: String = "right" if signf(_from(a, to, a.puppet.body_position()).x - tb.x) == to.motion._sign("arm_r") else "left"
		to.playing["receive"] = to.motion.play(actions()["receive"], {"side": their, "item": "@" + id})
		return true
	return false


## How far apart (px, in a's frame) a stands from b for a's fist, thrown straight out, to land on b's body: an
## arm and a part of the fist, and a little into b (its front, as far as its belly or chest comes out).
func _strike_gap(a: Actor, b: Actor) -> float:
	var mo: Motion = a.motion
	var k: float = space.scale_at(b.z) / maxf(space.scale_at(a.z), 0.001)
	return STRIKE_REACH * mo.arm + 0.4 * float(mo.hand_len["arm_r"]) + 0.6 * float(b.motion.front) * k


## The scene's light on this hero's present view: a shadow of its shape on the ground, a lit edge on its pictures.
func _dress_light(a: Actor) -> void:
	if not spec.has("light"):
		return
	Light.free_shadow(a.cast)
	a.cast = Light.make_shadow(a.puppet, light.shadow_root)
	var ls: Dictionary = spec["light"]
	var c: Array = ls.get("color", [1.0, 0.92, 0.75])
	a.rim = Light.rim_material(Vector2(-1.0, -1.0), float(ls.get("rim", 0.35)), Color(c[0], c[1], c[2]))
	# (the rim is a few px of the SCREEN wide: the pictures are drawn big and shown a third of their size or less)
	a.rim.set_shader_parameter("width", RIM_PX / maxf(absf(a.puppet.scale.y), 0.01))
	for part: Variant in a.puppet.parts.values():
		if part.name != "skirt":
			(part.sprite as Sprite2D).material = a.rim


func _light_step(a: Actor) -> void:
	if a.cast.is_empty():
		return
	var ls: Dictionary = spec["light"]
	var at: Array = ls.get("at", [0.5, 0.0])
	var lamp: Vector2 = space.transform_at(a.z).affine_inverse() * (Vector2(float(at[0]), float(at[1])) * world)
	var foot := Vector2(a.phys.pos.x, floor_y)
	var dir: float = signf(foot.x - lamp.x) if foot.x != lamp.x else 1.0
	# the lower the light and the further off to the side, the longer the shadow (a point light over the floor)
	var lean: float = clampf(absf(foot.x - lamp.x) / maxf(floor_y - lamp.y, 1.0), 0.12, 1.6) * float(ls.get("length", 0.8))
	Light.update_shadow(a.cast, space.transform_at(a.z) * Light.ground_transform(floor_y, dir, lean, 0.22),
			a.out == 0.0 and a.layer.visible)
	var head: Vector2 = a.motion._world_box("head").get_center()
	a.rim.set_shader_parameter("light_dir", (lamp - head).normalized())


## The top middle of a hero's head on the SCREEN (for a bubble over it, stars round it); null when it is off stage.
func _head_screen(id: String) -> Variant:
	var a: Actor = actors.get(id, null)
	if a == null or a.out != 0.0:
		return null
	var hb: Rect2 = _head_box(a)
	return camera.transform() * Vector2(hb.get_center().x, hb.position.y)


## A hero off the stage: beyond its edge (a.out), not drawn.
func _put_out(a: Actor) -> void:
	var sx: float = -OUT_MARGIN * a.leg if a.out < 0.0 else world.x + OUT_MARGIN * a.leg
	var x: float = space.frame_x(sx, a.z)
	var body: Vector2 = a.puppet.body_position()
	a.phys.pos.x = x                       # (the body follows its physics, the feet their places: as in a walk)
	for f: String in a.motion.foot_home:
		a.motion.foot_home[f].x += x - body.x
		a.puppet.set_target(f, a.motion.foot_home[f])
	a.layer.visible = false


## Whether this hero, as it stands now, goes over to its profile to work at the floor: seen from the front or the
## back, with a profile to turn to.
func _low_in_profile(a: Actor) -> bool:
	return a.view in ["front", "back"] and _view_dir(a, "side_r") != ""


## Standing (not lying, sitting or deep in a squat).
func _upright(a: Actor) -> bool:
	var mo: Motion = a.motion
	return absf(float(mo.chans["body"].now.get("lean", 0.0))) < 25.0 and float(mo.chans["legs"].now.get("drop", 0.0)) < 0.25 			and not mo.chans["legs"].now.has("seat")


## The arm of this hero on the side towards x.
static func _facing_arm(a: Actor, x: float) -> String:
	return "arm_r" if signf(x - a.puppet.body_position().x) == a.motion._sign("arm_r") else "arm_l"


## An action for two (its "pair": {"gap": arm lengths between the bodies' sides, "partner": the other's action,
## "view": "front" (side by side, facing us) | "face" (face to face, in profile where they have one), "over": true
## (this one is drawn over the other: its arm round the other's shoulders)}).
func _pair_command(a: Actor, line: Dictionary) -> void:
	var b: Actor = actors.get(str(line["with"]), null)
	if b == null or b == a:
		push_warning("stage: no partner '%s'" % str(line.get("with", "")))
		return
	var act: String = line["do"]
	var pair: Dictionary = actions()[act]["pair"]
	var face: bool = pair.get("view", "front") == "face" and _view_dir(a, "side_r") != "" and _view_dir(b, "side_r") != ""
	var me: Vector2 = a.puppet.body_position()
	var them: Vector2 = _from(b, a, b.puppet.body_position())
	var left_of: bool = me.x <= them.x                      # a stands to the left of b
	var gap: float = float(pair.get("gap", 0.6)) * 0.5 * (a.arm + b.arm * space.scale_at(b.z) / maxf(space.scale_at(a.z), 0.001))
	if face:
		gap += float(a.motion.front) + float(b.motion.front)
	else:
		gap += _half_width(a) + _half_width(b) * space.scale_at(b.z) / maxf(space.scale_at(a.z), 0.001)
	var want_x: float = them.x + (-gap if left_of else gap)
	if not line.get("_near", false) and (absf(want_x - me.x) > 0.12 * a.arm or absf(b.z - a.z) > 0.05 * a.leg):
		var then := line.duplicate()
		then["_near"] = true
		var go := {"who": a.id, "go": (space.vx + (want_x - space.vx) * space.scale_at(a.z)) / world.x,
				"depth": b.z / maxf(space.depth, 1.0), "_next": then}
		go["then"] = ("right" if left_of else "left") if face else "front"
		_command(go)
		return
	# side by side: both facing us; face to face: each turned to the other
	var b_view: String = ("left" if left_of else "right") if face else "front"
	if face and a.view != ("side_r" if left_of else "side_l"):
		_turn(a, "right" if left_of else "left")
		a.after.append(line)
		return
	if (b_view == "front" and b.view != "front") or (b_view != "front" and b.view != {"left": "side_l", "right": "side_r"}[b_view]):
		_turn(b, b_view)
		var again := line.duplicate()
		again["_near"] = true
		b.after.append(again)            # (run once b has turned: the line is still a's)
		return
	a.partner = b
	b.partner = a
	a.bias = -0.05 if pair.get("over", false) else 0.05
	b.bias = -a.bias
	var params := {}
	for k: String in ["energy", "speed", "duration"]:
		if line.has(k):
			params[k] = line[k]
	# each with its hand nearest the other (an action for two is written for the right hand); face to face in
	# profile both reach forward, the way they face
	var pa := params.duplicate()
	var pb := params.duplicate()
	pa["side"] = "right" if left_of or face else "left"
	pb["side"] = "left" if left_of and not face else "right"
	a.playing[act] = a.motion.play(actions()[act], pa)
	var other: String = str(pair.get("partner", act))
	if actions().has(other):
		b.playing[other] = b.motion.play(actions()[other], pb)


## Half the width of a hero's body as it stands (its chest or its belly, whichever is wider).
func _half_width(a: Actor) -> float:
	var w := 0.0
	for part: String in ["chest", "pelvis"]:
		if a.puppet.parts.has(part):
			w = maxf(w, a.motion._world_box(part).size.x * 0.5)
	return w


## "@partner" for a hero: places on the hero it does something with ("on"): "meet" (half way between their near
## shoulders, at the lower chest: a handshake), "meet_high" (the same, over the heads: a high five), "hand" (its near
## hand), "shoulder_near" / "shoulder_far" (the top of its shoulder), "waist_far" (its far side at the waist: an arm
## round it), "side_near" (its near side at the chest: a push).
func _partner_point(a: Actor) -> void:
	a.motion.points["@partner"] = func(ch: String, spec2: Dictionary) -> Vector2:
		var me: Vector2 = a.puppet.body_position()
		var b: Actor = a.partner
		if b == null:
			return me + Vector2(0.6 * a.arm * a.motion._sign(ch), 0.0)
		var bm: Motion = b.motion
		var bb: Vector2 = b.puppet.body_position()
		var toward: float = signf(_from(a, b, me).x - bb.x)        # which way a is from b (in b's frame)
		if toward == 0.0:
			toward = 1.0
		var near_ch: String = "arm_r" if signf(bm._sign("arm_r")) == toward else "arm_l"
		var far_ch: String = "arm_l" if near_ch == "arm_r" else "arm_r"
		var on: String = str(spec2.get("on", "meet"))
		var mine: Vector2 = a.motion._shoulder_at(ch, me)
		var theirs: Vector2 = _from(b, a, bm._shoulder_at(near_ch, bb))
		match on:
			"meet":
				return Vector2((mine.x + theirs.x) * 0.5, maxf(mine.y + 0.55 * a.arm, theirs.y + 0.55 * b.arm))
			"meet_high":
				return Vector2((mine.x + theirs.x) * 0.5, minf(mine.y, theirs.y) - 0.75 * a.arm)
			"hand":
				return _from(b, a, (b.puppet.parts["hand_" + near_ch.right(1)].node as Node2D).global_position)
			"shoulder_near":
				return theirs + Vector2(0.0, -0.1 * b.arm)
			"shoulder_far":
				# on the line of its shoulders, as far along it as this arm reaches (a wide partner: not the far
				# shoulder, but never across its chest either)
				var near_top: Vector2 = theirs + Vector2(0.0, -0.1 * b.arm)
				var far_top: Vector2 = _from(b, a, bm._shoulder_at(far_ch, bb) + Vector2(0.0, -0.1 * b.arm))
				var u := 1.0
				while u > 0.0 and mine.distance_to(near_top.lerp(far_top, u)) > 0.92 * a.arm:
					u -= 0.05
				return near_top.lerp(far_top, maxf(u, 0.0))
			"waist_far":
				var pb: Rect2 = bm._world_box("pelvis")
				return _from(b, a, Vector2(bb.x - toward * pb.size.x * 0.5, pb.position.y + 0.2 * pb.size.y))
			"side_near":
				var cb: Rect2 = bm._world_box("chest")
				return _from(b, a, Vector2(bb.x + toward * cb.size.x * 0.45, cb.get_center().y))
		return theirs


## "@meet" for a hero: half way to the nearest other hero, at the height of the lower chest of the two.
func _meet_point(a: Actor) -> void:
	a.motion.points["@meet"] = func(ch: String, spec2: Dictionary) -> Vector2:
		var me: Vector2 = a.puppet.body_position()
		var best: Actor = null
		for o: Actor in actors.values():
			if o != a and (best == null or absf(_from(o, a, o.puppet.body_position()).x - me.x) < absf(_from(best, a, best.puppet.body_position()).x - me.x)):
				best = o
		if best == null:
			return me + Vector2(0.6 * a.arm, 0.0)
		var them: Vector2 = _from(best, a, best.puppet.body_position())
		var their_y: float = _from(best, a, best.motion._shoulder_at("arm_r", best.puppet.body_position()) + Vector2(0.0, 0.55 * best.arm)).y
		var y: float = maxf(a.motion._shoulder_at(ch, me).y + 0.55 * a.arm, their_y)
		return Vector2((me.x + them.x) * 0.5, y)


## A "go": after the turn, the walk; after the walk, the turn back.
func _going(a: Actor) -> void:
	var g := a.going
	if g.is_empty() or not a.turning.is_empty():
		return
	match g["stage"]:
		"turn", "walk":
			# the way is across AND into the depth: the legs walk all of it, the body goes across only its share
			var dx: float = g["dx"]
			var path: float = Vector2(dx, g.get("dz", 0.0)).length()
			var across: float = absf(dx) / maxf(path, 1.0)
			var sgn: float = signf(dx) if dx != 0.0 else 1.0
			var dist: float = path / a.leg if a.view.begins_with("side") else sgn * path / a.leg
			var prm := {"dist": dist, "advance": across}
			if g["speed"] != null:
				prm["pace"] = float(g["speed"])   # (the walk's own speed: "speed" would speed up the whole action too)
			var style: String = g["style"] if actions().has(g["style"]) else "walk"
			g["run"] = a.motion.play(actions()[style], prm)
			g["stage"] = "walking"
		"walking":
			if not a.motion._gait.is_empty():
				a.z = lerpf(g.get("z0", a.z), g.get("z1", a.z), a.motion.walk_done())
			if (g["run"] as Object).done:
				a.z = g.get("z1", a.z)
				a.going = {}
				a.entering = false
				if a.leaving != 0.0:
					a.out = a.leaving              # gone over the edge: not drawn until it comes back
					a.leaving = 0.0
					_put_out(a)
				# the way it is to stand there; what comes next waits for that turn (if there is one to make)
				var want: String = {"left": "side_l", "right": "side_r"}.get(g["then"], g["then"])
				if g["then"] != "keep" and want != a.view and _turn(a, g["then"]) and not a.turning.is_empty():
					if not g["next"].is_empty():
						a.after.append(g["next"])
				elif not g["next"].is_empty():
					_command(g["next"])


## The floor of a scene without a background picture.
func _draw_ground(n: Node2D) -> void:
	if not spec.has("background"):
		n.draw_rect(Rect2(0, floor_y, world.x, world.y - floor_y), Color("e4dccb"))
		n.draw_line(Vector2(0, floor_y), Vector2(world.x, floor_y), Color("8a7f6c"), 3.0)


## A soft shadow on the ground under a hero (on its own layer: it shrinks with it in the depth).
func _draw_shadow(a: Actor) -> void:
	if a.phys == null:
		return
	var c := Vector2(a.phys.pos.x, floor_y + 4.0)
	# in the air the spot under the feet gets smaller and fainter, the higher the hero is
	var up: float = maxf(a.phys.stand_y - a.phys.pos.y, 0.0) / maxf(a.leg, 1.0)
	var k: float = 1.0 / (1.0 + 1.5 * up)
	var pts := PackedVector2Array()
	for i in 24:
		pts.append(c + Vector2(cos(TAU * i / 24.0) * a.leg * 0.75 * k, sin(TAU * i / 24.0) * a.leg * 0.10 * k))
	a.shadow.draw_colored_polygon(pts, Color(0, 0, 0, 0.28 * k))


func _process(_delta: float) -> void:
	for a: Actor in actors.values():
		if a.shadow != null:
			a.shadow.queue_redraw()


# ----------------------------------------------------------------------------- depth (engine/space.gd)

## Where a hero or a thing of the scene file stands: [x in the frame, depth z]. From "at" (a point), or "x" with
## "depth" (share of the ground) or "y" (where its feet are on the screen, share of the stage height).
func _ground_place(def: Dictionary, may_y := true) -> Vector2:
	var x0: Variant = def.get("x", 0.5)
	var sx: float = world.x * (float(x0) if not (x0 is String) else 0.5)
	if def.get("at", "") is String and points.has(def.get("at", "")):
		var pt: Dictionary = points[def["at"]]
		return space.ground_of(Vector2(world.x * float(pt["x"]), world.y * float(pt["y"])))
	var z := 0.0
	if def.has("near") and space.has_depth():      # nearer than the front edge: this many times its size there
		z = space.cam_d * (1.0 / maxf(float(def["near"]), 0.3) - 1.0)
	elif def.has("depth"):
		z = space.z_of_share(float(def["depth"]))
	elif may_y and def.has("y"):
		z = space.ground_of(Vector2(sx, SIZE.y * float(def["y"]))).y
	return Vector2(space.frame_x(sx, z), z)


## Where a "go" line sends a hero: [x in the frame, z].
func _go_target(a: Actor, line: Dictionary) -> Vector2:
	var go: Variant = line["go"]
	if go is String and go in ["out_left", "out_right"]:
		# off the stage: on until the whole hero is beyond that edge of the world
		var sx: float = -OUT_MARGIN * a.leg if go == "out_left" else world.x + OUT_MARGIN * a.leg
		return Vector2(space.frame_x(sx, a.z), a.z)
	if go is String and actors.has(go) and actors[go] != a:
		# up to another hero: to where a fist thrown at it lands on its body, on the side it is approached from
		var b: Actor = actors[go]
		var me: Vector2 = a.puppet.body_position()
		var them: Vector2 = _from(b, a, b.puppet.body_position())
		var dir: float = signf(them.x - me.x) if them.x != me.x else 1.0
		return Vector2(them.x - dir * _strike_gap(a, b), b.z)
	if go is String:
		if not points.has(go):
			push_warning("stage: no point '%s'" % go)
			return Vector2(a.puppet.body_position().x, a.z)
		var pt: Dictionary = points[go]
		return space.ground_of(Vector2(world.x * float(pt["x"]), world.y * float(pt["y"])))
	var z: float = a.z
	if line.has("depth"):
		z = space.z_of_share(float(line["depth"]))
	elif line.has("y"):
		z = space.ground_of(Vector2(world.x * float(go), world.y * float(line["y"]))).y
	return Vector2(space.frame_x(world.x * float(go), z), z)


## A set piece: a part of the background cut out, drawn over the same place, sorted in depth with the heroes.
func _add_piece(pd: Dictionary) -> void:
	var image := Image.load_from_file(_scene_file(pd["image"]))
	if image == null:
		return
	var r: Array = pd["rect"]
	var rect := Rect2(world.x * float(r[0]), world.y * float(r[1]), world.x * float(r[2]), world.y * float(r[3]))
	# the background under it painted clean (tools/cut_piece.py --moves), for a piece the life of the scene moves
	if pd.has("under"):
		var under := Image.load_from_file(_scene_file(pd["under"]))
		if under != null:
			var u := Sprite2D.new()
			u.texture = ImageTexture.create_from_image(under)
			u.centered = false
			u.position = rect.position
			u.scale = rect.size / Vector2(under.get_size())
			_back.add_child(u)
	# (a holder at the piece's corner, the picture in it: engine/life.gd moves the holder to the pivot it swings on)
	var holder := Node2D.new()
	holder.position = rect.position
	var s := Sprite2D.new()
	s.texture = ImageTexture.create_from_image(image)
	s.centered = false
	s.scale = rect.size / Vector2(image.get_size())
	holder.add_child(s)
	var layer := CanvasLayer.new()
	add_child(layer)
	layer.add_child(holder)
	var base: float = world.y * float(pd.get("base", r[1] + r[3]))
	var z: float = -INF if pd.get("front", false) else space.ground_of(Vector2(rect.get_center().x, base)).y
	# "bias": the order among things at the SAME depth (less = in front): a lamp on a desk shares the desk's depth
	# and is drawn over it, so a hero is either in front of the desk and all on it, or behind them all
	pieces.append({"id": pd.get("id", ""), "layer": layer, "z": z, "bias": float(pd.get("bias", 0.25))})
	_piece_nodes[pd.get("id", "")] = {"holder": holder, "sprite": s, "rect": rect}


## Each layer gets its depth's transform and its place in the drawing order (deeper first). At the same depth a
## hero is in front of a thing on the floor (the thing is at its feet) and of a set piece.
func _place_layers() -> void:
	var cam: Transform2D = camera.transform()
	_back.transform = cam * _slide(_back_scale())
	var order: Array = []                  # [z, bias, layer]
	var dof: Array = [[_back, _back_scale()]]
	for bd: Dictionary in _backdrops:
		(bd["layer"] as CanvasLayer).transform = cam * _slide(float(bd["scale"]))
		dof.append([bd["layer"], float(bd["scale"])])
	for a: Actor in actors.values():
		var sa: float = space.scale_at(a.z)
		a.layer.transform = cam * _slide(sa) * space.transform_at(a.z)
		dof.append([a.layer, sa])
		order.append([a.z, a.bias, a.layer])
		# the sides of the picture, in this hero's frame: deeper in, the picture spans more of the frame
		a.phys.walls = Vector2(space.frame_x(BodyPhysics.WALL, a.z), space.frame_x(world.x - BodyPhysics.WALL, a.z))
		if a.out != 0.0 or a.leaving != 0.0 or a.entering:
			a.phys.walls = Vector2(-1e6, 1e6)     # (walking out over an edge, or in from beyond it)
		if _haze.a > 0.0 and space.has_depth():
			a.puppet.modulate = _tint.lerp(_haze, _haze.a * a.z / space.depth)
	for id: String in _item_layers:
		var it: Variant = items.items.get(id, null)
		if it == null:
			continue
		var l: CanvasLayer = _item_layers[id]
		l.transform = cam * _slide(space.scale_at(it.z)) * space.transform_at(it.z)
		dof.append([l, space.scale_at(it.z)])
		order.append([it.z, 0.5, l])
		if _haze.a > 0.0 and space.has_depth():
			it.node.modulate = Color.WHITE.lerp(_haze, _haze.a * it.z / space.depth)
	for pc: Dictionary in pieces:
		var sp: float = _piece_scale(pc)
		(pc["layer"] as CanvasLayer).transform = cam * _slide(sp)
		order.append([pc["z"], float(pc.get("bias", 0.25)), pc["layer"]])
		dof.append([pc["layer"], sp])
	order.sort_custom(func(x: Array, y: Array) -> bool:
		if x[0] != y[0]:
			return x[0] > y[0]
		return x[1] > y[1])
	for i in order.size():
		(order[i][2] as CanvasLayer).layer = -90 + i
	if focus != null and focus.on:
		focus.step(1.0 / 60.0, _focus_scale(), dof, camera.zoom / camera.widest())


## Parallax: when the camera has moved off the middle of the world by d, a layer at depth scale s is shifted a further
## -(s - 1) d, so nearer layers slide past faster than the front edge and deeper ones slower (a real camera moving).
func _slide(s: float) -> Transform2D:
	if not parallax:
		return Transform2D.IDENTITY
	return Transform2D(0.0, -(s - 1.0) * (camera.center - world * 0.5))


func _add_backdrop(bd: Dictionary, i: int) -> void:
	var img := Image.load_from_file(_scene_file(str(bd["image"])))
	if img == null:
		return
	var layer := CanvasLayer.new()
	layer.layer = -120 + i
	add_child(layer)
	var spr := Sprite2D.new()
	img.generate_mipmaps()
	spr.texture = ImageTexture.create_from_image(img)
	spr.centered = false
	spr.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	var r: Array = bd.get("rect", [-0.2, 0.0, 1.4, 0.6])
	var rect := Rect2(world.x * float(r[0]), world.y * float(r[1]), world.x * float(r[2]), world.y * float(r[3]))
	spr.position = rect.position
	spr.scale = rect.size / Vector2(img.get_size())
	layer.add_child(spr)
	_backdrops.append({"layer": layer, "scale": float(bd.get("scale", 0.2))})


func _back_scale() -> float:
	return focus.back if focus != null and focus.on else (space.far_scale * 0.6 if space.has_depth() else 1.0)


func _piece_scale(pc: Dictionary) -> float:
	var z: float = pc["z"]
	return 1.6 if z == -INF else space.scale_at(z)


## The depth scale the focus is on now: a hero's (it may walk), the background's, or a number.
func _focus_scale() -> float:
	var t: Variant = focus.target
	if t is String:
		if t == "back":
			return _back_scale()
		if actors.has(t):
			return space.scale_at((actors[t] as Actor).z)
		return 1.0
	return float(t)


# ----------------------------------------------------------------------------- camera (engine/camera.gd)

func _camera_command(line: Dictionary) -> void:
	var kind: String = str(line["camera"])
	if kind == "shake":
		camera.shake(float(line.get("power", 1.0)), float(line.get("time", 0.4)))
		return
	_cam_line = line
	camera.move(float(line.get("time", 0.8)))


## A hero in the world (its depth applied): from the top of its head to its soles.
func _actor_box(a: Actor) -> Rect2:
	var t: Transform2D = space.transform_at(a.z)
	var s: float = space.scale_at(a.z)
	var head: Rect2 = a.motion._world_box("head")
	var soles: Vector2 = t * Vector2(a.phys.pos.x, floor_y)
	var top: float = (t * head.position).y
	var w: float = maxf(head.size.x, 1.2 * a.leg) * s
	return Rect2(Vector2(soles.x - 0.5 * w, top), Vector2(w, soles.y - top))


func _head_box(a: Actor) -> Rect2:
	var head: Rect2 = a.motion._world_box("head")
	return Rect2(space.transform_at(a.z) * head.position, head.size * space.scale_at(a.z))


## What the camera line asks for now: [centre, zoom, roll] (heroes move: asked again every step).
func _camera_goal() -> Array:
	var l := _cam_line
	var roll: float = deg_to_rad(float(l.get("roll", 0.0)))
	if l.has("zoom") or l.has("x") or l.has("y"):
		return [Vector2(world.x * float(l.get("x", 0.5)), world.y * float(l.get("y", 0.5))),
				camera.widest() * float(l.get("zoom", 1.0)), roll]
	var who: Array = []
	var on: Variant = l.get("on", [])
	for id: String in (on if on is Array else [str(on)]):
		if actors.has(id):
			who.append(actors[id])
	var kind: String = str(l.get("camera", "wide"))
	if who.is_empty() and kind != "wide":
		who = actors.values()
	if kind == "wide" or who.is_empty():
		var xs := 0.0
		var all := Rect2()
		for a: Actor in actors.values():
			var ab: Rect2 = _actor_box(a)
			xs += ab.get_center().x
			all = ab if all.size == Vector2.ZERO else all.merge(ab)
		var focus: float = xs / actors.size() if not actors.is_empty() else world.x * 0.5
		var w: Array = camera.wide(space.near_y, focus, all)
		return [w[0], w[1], roll]
	var box: Rect2 = _actor_box(who[0])
	var s_mean := 0.0
	for a: Actor in who:
		box = box.merge(_actor_box(a))
		s_mean += space.scale_at(a.z) / who.size()
	var f: Array
	match kind:
		"close":
			var hb: Rect2 = _head_box(who[0])
			f = camera.frame(hb, 0.42, 0.2)
		"medium":
			f = camera.frame(Rect2(box.position, Vector2(box.size.x, 0.62 * box.size.y)), 0.86, 0.08)
		"two":
			f = camera.frame(box.grow_individual(0.25 * box.size.y, 0.0, 0.25 * box.size.y, 0.0), 0.8, 0.1)
		_:
			f = camera.frame(box, 0.78, 0.1)
	if parallax and who.size() == 1:   # the hero slides by -(s - 1)(c - mid): aim where it will be seen
		f[0] = (f[0] + (s_mean - 1.0) * world * 0.5) / s_mean
	elif parallax:
		# several heroes at different depths slide by different amounts: find the centre that frames them as SEEN
		# (a damped fixed point: c -> frame of the boxes as they would be seen from c)
		var s_max := 1.0
		for a: Actor in who:
			s_max = maxf(s_max, space.scale_at(a.z))
		var c: Vector2 = f[0]
		for i in 24:
			var seen := Rect2()
			for a: Actor in who:
				var b: Rect2 = _actor_box(a)
				b.position -= (space.scale_at(a.z) - 1.0) * (c - world * 0.5)
				seen = b if seen.size == Vector2.ZERO else seen.merge(b)
			var g: Array = camera.frame(seen.grow_individual(0.25 * seen.size.y, 0.0, 0.25 * seen.size.y, 0.0), 0.8, 0.1) 					if kind == "two" else camera.frame(seen, 0.78, 0.1)
			c += (g[0] - c) / s_max
			f[1] = g[1]
		f[0] = c
	return [f[0], f[1], roll]


func _camera_step() -> void:
	if camera.on:
		var pic: Vector2 = _picture()
		if camera.started and pic != camera.screen:
			camera.started = false     # the window changed size (an HD film resizes it once it is up): no zoom ride
		camera.screen = pic
	camera.step(1.0 / 60.0, _camera_goal())
	if OS.has_environment("CAM_DEBUG") and step_no % 30 == 0:
		var seen := ""
		for a: Actor in actors.values():
			var sa: float = space.scale_at(a.z)
			var bx: Rect2 = _actor_box(a)
			seen += " %s s=%.2f x=%.0f->%.0f" % [a.id, sa, bx.get_center().x, bx.get_center().x - (sa - 1.0) * (camera.center.x - world.x * 0.5) if parallax else bx.get_center().x]
		print("CAM %d c=%s z=%.2f widest=%.2f%s" % [step_no, str(camera.center), camera.zoom, camera.widest(), seen])


## (for items.gd) the layer a hero is drawn on, and its depth
func layer_of(mo: Object) -> Node:
	for a: Actor in actors.values():
		if a.motion == mo:
			return a.layer
	return self


func z_of(mo: Object) -> float:
	for a: Actor in actors.values():
		if a.motion == mo:
			return a.z
	return 0.0


## (for items.gd) a thing's own layer while it is free, at its depth
func item_layer(it: Object) -> Node:
	if not _item_layers.has(it.id):
		var l := CanvasLayer.new()
		add_child(l)
		_item_layers[it.id] = l
	var layer: CanvasLayer = _item_layers[it.id]
	layer.transform = camera.transform() * space.transform_at(it.z)
	return layer


## A point of one layer's frame in another's (the same unless their depths differ).
func move_point(p: Vector2, from: Node, to: Node) -> Vector2:
	var tf: Transform2D = (from as CanvasLayer).transform if from is CanvasLayer else Transform2D.IDENTITY
	var tt: Transform2D = (to as CanvasLayer).transform if to is CanvasLayer else Transform2D.IDENTITY
	return tt.affine_inverse() * (tf * p)


## A point of hero `src`'s frame in hero `dst`'s.
func _from(src: Actor, dst: Actor, p: Vector2) -> Vector2:
	return move_point(p, src.layer, dst.layer)
