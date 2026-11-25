extends "res://stage.gd"
## The VIEWER: one hero on an empty stage and every action as a button, to look at what the engine can do.
##
##   godot --path engine res://viewer.tscn -- --hero=<slug> --puppets=<world>/heroes
##
## On the right: the hero, the view (front / left / right / back), an item into the hand or onto the floor, side,
## strength and speed, "to rest"; then all the actions of engine/actions by group, under their own titles. An
## action that needs a thing (take, lift, drink, drive: "test_items" in its file) gets that thing by itself; a walk
## (run, sneak...) goes to the far side of the stage; actions for two heroes are left out.
## The stage is the usual one (stage.gd): what is seen here is what a scene will show.

const HERO := "hero"
const GROUPS := {"pose": "Позы", "gesture": "Жесты", "body": "Тело", "move": "Перемещение", "feeling": "Чувства",
	"dance": "Танцы", "item": "Предметы", "fight": "Драка", "silly": "Дурачества", "music": "Музыка", "two": "Вдвоём"}
const ITEM_NAMES := {"mug": "кружка", "ball": "мяч", "crate": "ящик", "book": "книга", "wheel": "руль", "sword": "меч",
	"shovel": "лопата", "guitar": "гитара", "balalaika": "балалайка", "drum": "барабан", "accordion": "гармошка",
	"bass": "контрабас", "pipe": "дудочка"}

static var hero_name := "sumo"
## The folder the heroes are in: --puppets=<folder> (the studio kit passes the world's heroes), else ../puppets.
static var puppets_root := ""
static var live_mouth := 0         # the panel's "live mouth": 0 none, 1 the oval (scenes/mouth_demo), 2 the lips alone (scenes/lips_demo)

var _side := "right"
var _elbow_say := ""           # "" = the engine chooses; else every arm pose of the next action gets this "elbow"
var _energy := 1.0
var _speed := 1.0
var _status: Label
var _item_pick: OptionButton


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--hero=") and preset.is_empty():
			hero_name = a.trim_prefix("--hero=")
		elif a.begins_with("--puppets="):
			puppets_root = a.trim_prefix("--puppets=")
	if puppets_root.is_empty() and hero_name.is_absolute_path():
		# a hero given by its folder: the list beside it is its neighbours (heroes/<slug>/puppet -> heroes/)
		var d := hero_name.simplify_path()
		puppets_root = d.get_base_dir().get_base_dir() if d.get_file() == "puppet" else d.get_base_dir()
	var me := {"id": HERO, "puppet": _hero_dir(hero_name), "x": 0.5, "height": 0.3}
	if live_mouth > 0 and FileAccess.file_exists(_mouth_clip()):
		me["mouth"] = _mouth_clip()              # a recorded mouth on the painted face (lab/mouth_clip.py)
	preset = {"floor": 0.82, "seconds": 99999, "actors": [me], "items": [], "script": []}
	camera_on = false              # the stage as it is, the panel beside it
	super._ready()
	_elbow_say = OS.get_environment("VIEWER_ELBOW")      # (for checks: the panel's "elbow" choice from outside)
	_build_panel()


## (for checking the window itself: VIEWER_SHOT=<file.png> saves a picture of it after a second and quits;
## VIEWER_PLAY=<action id> presses that action first, VIEWER_GIVE=<item> puts that item into the hand first)
func _process(delta: float) -> void:
	super._process(delta)
	if not OS.has_environment("VIEWER_SHOT") and not OS.has_environment("VIEWER_SEQ"):
		return
	_frames += 1
	# VIEWER_SEQ="wave@30,head_grab@140,...": presses those actions at those frames (to hunt for what a chain of
	# actions breaks); quits 200 frames after the last
	if OS.has_environment("VIEWER_SEQ"):
		if _seq.is_empty() and _frames == 1:
			for part in OS.get_environment("VIEWER_SEQ").split(","):
				_seq.append([int(part.get_slice("@", 1)), part.get_slice("@", 0)])
		for e: Array in _seq:
			if e[0] == _frames:
				if e[1] == "REST":
					_rest()
				else:
					_play(e[1])
		if not _seq.is_empty() and _frames == int(_seq[-1][0]) + 200 and not OS.has_environment("VIEWER_SHOT"):
			get_tree().quit()
		if not OS.has_environment("VIEWER_SHOT"):
			return
	if _frames == 20 and OS.has_environment("VIEWER_GIVE"):
		_give(OS.get_environment("VIEWER_GIVE"), true)
	if _frames == 20 and OS.has_environment("VIEWER_PLAY"):
		_play(OS.get_environment("VIEWER_PLAY"))
	if _frames == int(OS.get_environment("VIEWER_AT")) if OS.has_environment("VIEWER_AT") else _frames == 60:
		get_viewport().get_texture().get_image().save_png(OS.get_environment("VIEWER_SHOT"))
		get_tree().quit()


var _frames := 0
var _seq: Array = []


# ----------------------------------------------------------------------------- the panel

func _build_panel() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 20
	add_child(layer)
	var root := PanelContainer.new()
	root.position = Vector2(SIZE.x + 8, 8)
	root.size = Vector2(700, SIZE.y - 16)
	var theme := Theme.new()
	theme.default_font_size = 25
	# flat and light, like the stage: no borders, no shadows, no grey
	var ink := Color("2a2622")
	root.add_theme_stylebox_override("panel", _flat(Color("f4efe6"), 0))
	for kind: String in ["Button", "OptionButton"]:
		theme.set_stylebox("normal", kind, _flat(Color("e2d6bf"), 8))
		theme.set_stylebox("hover", kind, _flat(Color("d6c7a8"), 8))
		theme.set_stylebox("pressed", kind, _flat(Color("c4b08a"), 8))
		theme.set_stylebox("focus", kind, _flat(Color(0, 0, 0, 0), 8))
		for c: String in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
			theme.set_color(c, kind, ink)
	theme.set_color("font_color", "Label", ink)
	theme.set_stylebox("panel", "PopupMenu", _flat(Color("f4efe6"), 6))
	theme.set_color("font_color", "PopupMenu", ink)
	theme.set_color("font_hover_color", "PopupMenu", ink)
	theme.set_stylebox("hover", "PopupMenu", _flat(Color("d6c7a8"), 4))
	theme.set_stylebox("slider", "HSlider", _flat(Color("d6c7a8"), 4))
	theme.set_stylebox("grabber_area", "HSlider", _flat(Color("b89f6d"), 4))
	theme.set_stylebox("grabber_area_highlight", "HSlider", _flat(Color("b89f6d"), 4))
	root.theme = theme
	layer.add_child(root)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	root.add_child(col)

	# the hero
	var heroes := OptionButton.new()
	var names: Array = _heroes()
	for n: String in names:
		heroes.add_item(n + _lacks(n))
	heroes.select(maxi(names.find(hero_name), 0))
	heroes.item_selected.connect(func(i: int) -> void:
		hero_name = names[i]
		get_tree().reload_current_scene())
	col.add_child(_row("Герой", [heroes, _button("Живой рот: " + ["нет", "овал", "губы"][live_mouth], func() -> void:
		live_mouth = (live_mouth + 1) % 3
		get_tree().reload_current_scene())]))

	# the view
	var views: Array = []
	for v: Array in [["Спереди", "front"], ["Влево", "left"], ["Вправо", "right"], ["Сзади", "back"]]:
		views.append(_button(v[0], func() -> void: _command({"who": HERO, "turn": v[1]})))
	col.add_child(_row("Вид", views))

	# an item
	_item_pick = OptionButton.new()
	for id: String in ITEM_NAMES:
		_item_pick.add_item(ITEM_NAMES[id])
	col.add_child(_row("Предмет", [_item_pick,
		_button("в руку", func() -> void: _give(ITEM_NAMES.keys()[_item_pick.selected], true)),
		_button("на пол", func() -> void: _give(ITEM_NAMES.keys()[_item_pick.selected], false)),
		_button("убрать", func() -> void: items.remove("item"))]))

	# how
	var side := OptionButton.new()
	for sname: String in ["правая", "левая", "обе"]:
		side.add_item(sname)
	side.item_selected.connect(func(i: int) -> void: _side = ["right", "left", "both"][i])
	var energy := _slider(0.5, 1.6, 1.0, func(v: float) -> void: _energy = v)
	var speed := _slider(0.5, 1.6, 1.0, func(v: float) -> void: _speed = v)
	col.add_child(_row("Сторона", [side]))
	# where the elbow points: the engine's own choice, or said outright (the action's "elbow")
	var elbow := OptionButton.new()
	for ename: String in ["сам (авто)", "вниз", "вверх", "наружу", "внутрь"]:
		elbow.add_item(ename)
	elbow.item_selected.connect(func(i: int) -> void: _elbow_say = ["", "down", "up", "out", "in"][i])
	col.add_child(_row("Локоть", [elbow]))
	col.add_child(_row("Сила", [energy]))
	col.add_child(_row("Скорость", [speed]))
	col.add_child(_button("В покой (остановить всё)", _rest))

	# the actions
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	col.add_child(scroll)
	var list := VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)
	var by_group := {}
	for id: String in actions():
		var a: Dictionary = actions()[id]
		if a.get("two", false) or id == "rest" or id.begins_with("_"):
			continue
		by_group.get_or_add(a.get("group", "other"), []).append(id)
	for g: String in GROUPS.keys() + by_group.keys().filter(func(k: String) -> bool: return not GROUPS.has(k)):
		if not by_group.has(g):
			continue
		var title := Label.new()
		title.text = GROUPS.get(g, g)
		title.add_theme_font_size_override("font_size", 28)
		list.add_child(title)
		var grid := GridContainer.new()
		grid.columns = 2
		grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		list.add_child(grid)
		var ids: Array = by_group[g]
		ids.sort()
		for id: String in ids:
			var b := _button(actions()[id].get("title", id), func() -> void: _play(id))
			b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			b.tooltip_text = id
			grid.add_child(b)

	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.text = "Нажмите действие"
	col.add_child(_status)


static func _flat(colour: Color, radius: int) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = colour
	sb.set_corner_radius_all(radius)
	sb.content_margin_left = 12
	sb.content_margin_right = 12
	sb.content_margin_top = 6
	sb.content_margin_bottom = 6
	return sb


func _row(title: String, controls: Array) -> HBoxContainer:
	var row := HBoxContainer.new()
	var l := Label.new()
	l.text = title
	l.custom_minimum_size = Vector2(130, 0)
	row.add_child(l)
	for c: Control in controls:
		c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(c)
	return row


func _button(text: String, on_press: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.pressed.connect(on_press)
	return b


func _slider(lo: float, hi: float, value: float, on_change: Callable) -> HSlider:
	var s := HSlider.new()
	s.min_value = lo
	s.max_value = hi
	s.step = 0.05
	s.value = value
	s.custom_minimum_size = Vector2(0, 34)
	s.value_changed.connect(on_change)
	return s


## What a hero has no drawings for, as a note for the list: a fist (punches, holding things), a side view (walks,
## fights, sitting: they are played from the front instead, or not at all).
func _lacks(name: String) -> String:
	var dir: String = _hero_dir(name)
	var notes: Array = []
	if not FileAccess.file_exists(dir.path_join("parts/hand_r.fist.png")):
		notes.append("нет кулака")
	if not FileAccess.file_exists(dir.path_join("side/rig.json")):
		notes.append("нет профиля")
	if not FileAccess.file_exists(dir.path_join("back/rig.json")):
		notes.append("нет вида сзади")
	return "" if notes.is_empty() else "   (" + ", ".join(notes) + ")"


## What this action needs that the hero on the stage has not got (said under the list when it is pressed).
func _missing(act: Dictionary) -> String:
	var a := _hero()
	var notes: Array = []
	var fist := false
	for ph: Dictionary in act.get("phases", []):
		for k: String in ["arm_l", "arm_r", "arms"]:
			if ph.get(k, null) is Dictionary and ph[k].get("look", "") == "fist":
				fist = true
	for d: Dictionary in act.get("test_items", []):
		fist = fist or d.get("card", "") not in ["ball", "crate"]
	if fist and not a.puppet.parts["hand_r"].skins.has("fist"):
		notes.append("у героя не нарисован кулак (tadam.puppet.gen_hands, kind fist): " + hero_name)
	if act.get("view", "") == "side" and _view_dir(a, "side_r") == "":
		notes.append("у героя нет вида в профиль: действие сыграно спереди (" + hero_name + ")")
	return "" if notes.is_empty() else "
НЕ ХВАТАЕТ: " + "; ".join(notes)


## The sample recorded mouth (a lab recording; not in the kit: the panel's live mouth stays off without it).
static func _mouth_clip() -> String:
	return ProjectSettings.globalize_path("res://").path_join("../scenes/%s/mouth.ogv" % ("lips_demo" if live_mouth == 2 else "mouth_demo")).simplify_path()


## A hero's puppet folder: <puppets>/<name>, or <puppets>/<name>/puppet in a world folder (heroes/<slug>/puppet);
## a name that is an absolute path is the folder itself.
static func _hero_dir(name: String) -> String:
	if name.is_absolute_path():
		return name.simplify_path()
	var d: String = _puppets().path_join(name)
	if FileAccess.file_exists(d.path_join("puppet").path_join("rig.json")):
		d = d.path_join("puppet")
	return d.simplify_path()


static func _puppets() -> String:
	if not puppets_root.is_empty():
		return puppets_root.simplify_path()
	return ProjectSettings.globalize_path("res://").path_join("../puppets").simplify_path()


## Every hero that has been cut (puppets/<name>/rig.json).
func _heroes() -> Array:
	var dir: String = _puppets()
	var out: Array = []
	for d in DirAccess.get_directories_at(dir):
		if not d.begins_with("_") and FileAccess.file_exists(_hero_dir(d).path_join("rig.json")):
			out.append(d)
	out.sort()
	return out


# ----------------------------------------------------------------------------- doing

func _hero() -> Actor:
	return actors[HERO]


## One item at a time, called "item": into the hand of the chosen side (both for a thing held with both), or onto
## the floor within reach on that side.
func _give(card: String, into_hand: bool) -> void:
	items.remove("item")
	var a := _hero()
	var arm_ch: String = "arm_l" if _side == "left" else "arm_r"
	var x: float = a.puppet.body_position().x + 0.6 * a.arm * a.motion._sign(arm_ch)
	if FileAccess.file_exists("res://items/%s.json" % card):
		var def: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://items/%s.json" % card))
		if str(def.get("hold", "")) == "both" and not into_hand:
			x = a.puppet.body_position().x          # a thing lifted with both hands stands in front of the hero
	items.add("item", card, Vector2(x, floor_y - 60.0))
	if into_hand:
		items.hold_now(a.motion, "hand_l" if _side == "left" else "hand_r", "item")
	_say("%s %s" % [ITEM_NAMES.get(card, card), "в руке" if into_hand else "на полу"])


func _held_card() -> String:
	if items.items.has("item") and items.items["item"].holder != null:
		return items.items["item"].def.get("id", "")
	return ""


func _play(id: String) -> void:
	var a := _hero()
	var act: Dictionary = actions()[id]
	var side: String = _side if act.get("params", {}).has("side") else "right"
	if act.get("group", "") == "music":
		# an instrument: the hero gets it and plays it (stage.gd "play")
		items.remove("item")
		_command({"who": HERO, "play": act["test_items"][0]["card"], "for": 4.0, "energy": _energy, "speed": _speed})
		_say("%s  (%s)%s" % [act.get("title", id), id, _missing(act)])
		return
	# the thing the action is about, if it needs one
	for d: Dictionary in act.get("test_items", []):
		var card: String = d["card"]
		if d.has("held"):
			if _held_card() != card:
				var keep := _side
				_side = "left" if side == "left" else "right"
				_give(card, true)
				_side = keep
		elif not items.items.has("item") or items.items["item"].holder != null or items.items["item"].def.get("id", "") != card:
			_give(card, false)
	var line := {"who": HERO, "energy": _energy, "speed": _speed}
	if act.get("params", {}).has("side"):
		line["side"] = side
	match id:
		"take", "lift":
			line["take"] = "item"
		"put":
			line["put"] = true
		"throw":
			line["throw"] = true
		_:
			if act.get("group", "") == "move" and _walks(act):
				# a walk: to the far side of the stage, in this gait
				line["go"] = 0.15 if a.puppet.body_position().x > SIZE.x * 0.5 else 0.85
				line["style"] = id
				line.erase("speed")
			else:
				line["do"] = _with_elbow(id)
				line["duration"] = 2.5
	_command(line)
	_say("%s  (%s)%s" % [act.get("title", id), id, _missing(act)])


## The action itself, or (an elbow chosen on the panel) a copy of it with that "elbow" in every arm pose.
func _with_elbow(id: String) -> String:
	if _elbow_say == "":
		return id
	var copy: Dictionary = actions()[id].duplicate(true)
	copy["id"] = "_try"
	for ph: Dictionary in copy.get("phases", []):
		for k: String in ["arm_l", "arm_r", "arms"]:
			if ph.get(k, null) is Dictionary:
				ph[k]["elbow"] = _elbow_say
	actions()["_try"] = copy
	return "_try"


static func _walks(act: Dictionary) -> bool:
	for ph: Dictionary in act.get("phases", []):
		if ph.get("legs", null) is Dictionary and ph["legs"].has("walk"):
			return true
	return false


func _rest() -> void:
	var a := _hero()
	_command({"who": HERO, "play": "off"})
	a.playing.clear()
	a.going = {}
	a.motion.rest_all()
	_say("в покое")


func _say(text: String) -> void:
	if _status != null:
		_status.text = text
