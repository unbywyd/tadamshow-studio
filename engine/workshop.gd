extends "res://stage.gd"
## THE WORKSHOP (docs: mechanics-tz.md, skill/reference/mechanics.md): look at the heroes and their mechanics, and
## make an action out of poses set by hand.
##
##   tadam workshop [hero]          (it writes the config and opens this scene: --config=<file.json>)
##
## The stage on the left with its clock under the hero (pause, a frame, 0.25x / 0.5x / 1x, round and round, the
## trail of the hands and feet, breathing); the panel on the right: who is on the stage, and two modes:
##   ДЕЙСТВИЯ   every action of the library and of this world as tiles by group, with a search; how to play it
##              (side, elbow, strength, speed); a CLEAN switch by default (everything lets go and goes to rest
##              first: motion.gd play_clean), or laid over what plays; what plays now; the faults the hero check
##              found in this action, in words.
##   ИЗ ПОЗ     dots on the hero: the hands, the feet, the pelvis (down / aside), the neck (the lean), the head;
##              right click on a hand: palm / fist / back / edge / point; the wheel turns the wrist; Shift + right
##              click: where the elbow points. «Запомнить позу» (F) keeps it; every pose is a card with its way in
##              (time, ease, hold); «Показать движение» plays them; «Сохранить» writes an action of this world
##              (actions/<id>.json), or of the core library with --core.
## Design (the owner's taste): flat and matte, no borders, no shadows, no grey; one ink, deep blue for what is
## chosen, red only for the main button and for faults; every state of every control is set.
## The files are the only truth: an action file changed on disk (by Claude) is read again at once; what is chosen
## and the pose list are written to <world>/.tadam/workshop/state.json for Claude, and `tadam workshop pose --fix`
## asks through cmd.json.

const MotionScript := preload("res://motion.gd")
const GROUP_TITLES := {"pose": "Позы", "gesture": "Жесты", "body": "Тело", "move": "Перемещение", "feeling": "Чувства",
	"dance": "Танцы", "item": "С предметами", "fight": "Драка", "silly": "Дурачества", "music": "Музыка", "two": "Вдвоём"}
const LOOKS := ["auto", "palm", "fist", "back", "edge", "point"]
const LOOK_NAMES := {"auto": "сама", "palm": "ладонь", "fist": "кулак", "back": "тыльная", "edge": "ребро", "point": "палец"}
const ELBOWS := ["", "down", "up", "out", "in"]
const ELBOW_NAMES := {"down": "локоть вниз", "up": "локоть вверх", "out": "локоть наружу", "in": "локоть внутрь"}
const EASES := ["inout", "out", "in", "linear"]
const EASE_NAMES := ["Плавно", "Резкий старт", "Резкий конец", "Ровно"]
## The hero check's measures in words (engine/tools/action_check.gd LIMITS)
const FAULT_WORDS := {"wrong": "локоть или колено выгнулись не в ту сторону", "slide": "стоящая стопа скользит",
	"inside": "кисть уходит в корпус", "floor": "что-то проваливается под пол", "miss": "кисть не дошла до места",
	"path": "кисть идёт в обход, а не прямо", "accel": "рывок кисти", "out": "уходит из кадра",
	"face": "рука закрывает лицо", "back": "не вернулся в покой", "balance": "теряет равновесие",
	"grab": "промахнулся мимо предмета", "nograb": "не взял предмет, который должен был взять",
	"item_floor": "предмет уходит под пол", "cross": "локоть неудачно переходит на другую сторону",
	"skirt": "юбка проходит сквозь ноги", "torn": "юбка рвётся", "jerk": "дёргается"}
const DOT_NAMES := {"hand_l": "левая кисть", "hand_r": "правая кисть", "foot_l": "левая стопа", "foot_r": "правая стопа",
	"body": "таз: присесть, сдвинуться", "neck": "середина плеч: наклон корпуса", "head": "макушка: вбок — наклон, вниз — втянуть голову",
	"shoulder_l": "левое плечо: вверх — поднять", "shoulder_r": "правое плечо: вверх — поднять"}
const PANEL_W := 760.0
const DOT := 14.0
const REACH := 40.0
const TRAIL := 120                  # steps of the trail
const HAND_PACE := 1.6              # arm lengths a second: the time a pose's way in gets by default

## the palette (one system: see the header)
const C_PAPER := Color("f2efe9")    # the panel
const C_CARD := Color("fbfaf7")     # a card on it
const C_CONTROL := Color("e4ded3")  # a button at rest
const C_HOVER := Color("d8d0c2")
const C_INK := Color("1e2330")
const C_SOFT := Color("596070")     # notes
const C_CHOSEN := Color("22506a")   # chosen (deep blue), white text
const C_CHOSEN_HOVER := Color("1b4257")
const C_MAIN := Color("b3362c")     # the main button, faults
const C_MAIN_HOVER := Color("9c2e25")
const C_FAULT_BG := Color("f5e1dc")
const C_DOT_LIMB := Color("22506a")
const C_DOT_BODY := Color("b3362c")

## kept across a reload of the scene (changing the hero or the row)
static var cfg: Dictionary = {}
static var row := "one"             # "one" | "all" | "proof" | "pair"
static var hero_id := ""            # (in a pair: the one on the left, who leads)
static var partner_id := ""         # a pair: the one on the right
static var pair_x: Array = [0.37, 0.63]   # a pair: where each stands, a share of the stage's width (dragged by
                                    # the handle under its feet, or the «Расстояние» slider)
static var pair_edit := 0           # a pair: whose pose the dots change (0 the left one, 1 the right one)
static var pair_pose: Array = [{}, {}]   # a pair: the pose of each (pose_now is the edited one's)
static var tab := 0                 # 0 actions, 1 poses
static var poses: Array = []        # [{pose, time, ease, hold}]
static var pose_now: Dictionary = {}
static var chosen := ""             # the action chosen last
static var _cmd_seen := 0
static var still := false           # the idle life (breath, sway) off: a pose stands exactly still
static var _sized := false
static var proof_pick: Array = ["proof:plain", "proof:tall", "proof:heavy", "proof:skirt_floor"]   # at most PROOF_MAX side by side
const PROOF_MAX := 4

var _side := "right"
var _elbow_say := ""
var _energy := 1.0
var _speed := 1.0
var speed := 1.0                    # the clock: 0.25 / 0.5 / 1
var paused := false
var _steps_wanted := 0
var _acc := 0.0
var _over_mode := false             # laid over what plays, instead of a clean switch
var _loop := false
var _trails := false
var _pending: Dictionary = {}       # a line waiting for the clean switch to reach rest
var _due_lines: Array = []
var _idle := 0
var _trail: Dictionary = {}         # handle -> [points]
var _drag := ""
var _drag_off := Vector2.ZERO
var _hover := ""
var _sel := -1                      # the pose card being edited
var _stamp := ""
var _poll := 0.0
var _dirty_state := true

var _status: Label
var _faults: PanelContainer
var _faults_text: Label
var _playing_box: HFlowContainer
var _tiles: VBoxContainer
var _tile_of: Dictionary = {}       # action id -> its button
var _search: LineEdit
var _how_card: Control
var _front_seg: HBoxContainer
var _panel_bg: Control
var _panel_want := Vector2.ZERO
var _below: ColorRect               # under the stage when the window is taller than it
var _elbow_seg: HBoxContainer
var _tiles_scroll: ScrollContainer
var _how_hint: Label
var _how_title: Label                # «Как сыграть «…»»: what the card's buttons change
var _how_note: Label
var _side_row: Control
var _elbow_row: Control
var _modes: Array = []              # the two mode buttons
var _pages: Array = []              # the two pages
var _pose_cards: VBoxContainer
var _save_id: LineEdit
var _save_title: LineEdit
var _pause_btn: Button
var _dots: Node2D
var _head_font: Font


class Dots extends Node2D:
	var ws: Node
	func _draw() -> void:
		ws._draw_dots(self)


func _ready() -> void:
	if cfg.is_empty():
		var path := ""
		for a in OS.get_cmdline_user_args():
			if a.begins_with("--config="):
				path = a.trim_prefix("--config=")
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if path != "" else null
		cfg = parsed if parsed is Dictionary else {}
		hero_id = str(cfg.get("hero", ""))
		if cfg.get("actions_dir", "") != "":
			world_actions_dir = str(cfg["actions_dir"])
			_actions.clear()
		_load_poses()
	var heroes := _row_heroes()
	var acts: Array = []
	var fit := (SIZE.x / (heroes.size() + 0.6)) / 0.62 / SIZE.y     # (a body with its arms out is about 0.6 of its height wide)
	for i in heroes.size():
		var h: Dictionary = heroes[i]
		var x: float = (i + 0.8) / (heroes.size() + 0.6)
		if row == "pair":                        # (a pair: side by side, as far apart as the slider says)
			x = float(pair_x[i])
		acts.append({"id": h["id"], "puppet": h["dir"], "x": x,
			"height": minf(float(h.get("height", 0.36)), fit)})
	preset = {"floor": 0.84, "seconds": 99999, "actors": acts, "items": [], "script": []}
	# the window's base is the stage AND the panel: a narrower window shrinks both, a wider one widens the panel
	get_tree().root.content_scale_size = Vector2i(int(SIZE.x + PANEL_W), int(SIZE.y))
	camera_on = false
	super._ready()
	set_physics_process(true)
	var where := "%s|%s|%s|%s" % [str(cfg.get("world", "")), hero_id, row, partner_id if row == "pair" else ""]
	if where != _logged_where:
		_log("open" if _logged_where == "" else "hero", "рубрика «%s» · %s" % [str(cfg.get("world_title", "")),
			"все герои" if row == "all" else ("пробные тела" if row == "proof" else (_pair_words() if row == "pair" else "герой «%s»" % str(_hero_def(hero_id).get("title", hero_id))))])
		_logged_where = where
	_fit_window()
	_dots = Dots.new()
	_dots.ws = self
	_dots.z_index = 4000
	add_child(_dots)
	_head_font = _load_head_font()
	_build_panel()
	_build_clock()
	if pose_now.is_empty():
		pose_now = rest_pose()
	if row == "pair":
		if (pair_pose[0] as Dictionary).is_empty() and (pair_pose[1] as Dictionary).is_empty():
			pair_pose[pair_edit] = pose_now      # (into a pair from one hero: its pose stays with it)
		pose_now = _pose_for(pair_edit)
		_show_front()
	var replay := chosen                  # (_show_mode puts everyone at rest, and that forgets the chosen action)
	_show_mode(tab)
	if tab == 0 and replay != "" and actions().has(replay):
		_play.call_deferred(replay)
	_stamp = _actions_stamp()
	_set_life()
	_write_state()


## The window takes most of the screen's height (the stage 720 and the panel side by side, 1280 high).
func _fit_window() -> void:
	if _sized or DisplayServer.get_name() == "headless" or OS.has_environment("WORKSHOP_SEQ"):
		return
	_sized = true
	var usable := DisplayServer.screen_get_usable_rect()
	var h := mini(int(usable.size.y * 0.94), 1280)
	var w := int(h * (SIZE.x + PANEL_W) / SIZE.y)
	DisplayServer.window_set_size(Vector2i(w, h))
	DisplayServer.window_set_position(usable.position + (usable.size - Vector2i(w, h)) / 2)


static func _load_head_font() -> Font:
	var f := ProjectSettings.globalize_path("res://").path_join("../src/tadam/data/fonts/PT_Serif-Web-Bold.ttf").simplify_path()
	if FileAccess.file_exists(f):
		var ff := FontFile.new()
		if ff.load_dynamic_font(f) == OK:
			return ff
	return null


func _set_life() -> void:
	for a: Actor in actors.values():
		if a.motion != null:
			a.motion.life = 0.0 if still else 1.0


# ----------------------------------------------------------------------------- the heroes

func _row_heroes() -> Array:
	var world: Array = cfg.get("heroes", [])
	var proof: Array = cfg.get("proof", [])
	if row == "all" and not world.is_empty():
		return world
	if row == "proof" and not proof.is_empty():
		var some := proof.filter(func(h: Dictionary) -> bool: return proof_pick.has(h["id"]))
		return some if not some.is_empty() else proof.slice(0, PROOF_MAX)
	if row == "pair":
		var pool: Array = _pair_pool()
		if pool.size() >= 2:
			var ids: Array = pool.map(func(h: Dictionary) -> String: return h["id"])
			if not ids.has(hero_id):
				hero_id = ids[0]
			if not ids.has(partner_id) or partner_id == hero_id:
				partner_id = ids[1] if ids[0] == hero_id else ids[0]
			return [pool[ids.find(hero_id)], pool[ids.find(partner_id)]]
		row = "one"
	for h: Dictionary in world + proof:
		if h["id"] == hero_id:
			return [h]
	if not world.is_empty():
		hero_id = world[0]["id"]
		return [world[0]]
	if not proof.is_empty():
		hero_id = proof[0]["id"]
		return [proof[0]]
	return []


## Who can stand in a pair: the rubric's heroes (and the proof bodies, when the rubric has fewer than two).
func _pair_pool() -> Array:
	var world: Array = cfg.get("heroes", [])
	return world if world.size() >= 2 else world + cfg.get("proof", [])


## The hero whose pose the dots change: in a pair the one picked («Правлю позу»), else the main one.
func _edited() -> Actor:
	if row == "pair":
		var id: String = hero_id if pair_edit == 0 else partner_id
		if actors.has(id):
			return actors[id]
	return _main()


## A pair: this far apart, about the middle between them.
func _set_pair_dx(d: float) -> void:
	var mid: float = (float(pair_x[0]) + float(pair_x[1])) * 0.5
	mid = clampf(mid, 0.05 + d * 0.5, 0.95 - d * 0.5)
	pair_x = [snappedf(mid - d * 0.5, 0.005), snappedf(mid + d * 0.5, 0.005)]


## THE ⇆ UNDER A HERO'S FEET (a pair): dragged along the floor, the hero stands there (the scene is laid out
## again on release; the two never swap sides: the left one leads).
var _stand_drag := -1
var _stand_at := 0.0


func _stand_point(k: int) -> Vector2:
	var a := _pair_actor(k)
	if a == null:
		return Vector2(-INF, -INF)
	return Vector2(a.motion._rest_body.x, floor_y + 22.0)


func _stand_to(k: int, x: float) -> void:
	var share: float = x / SIZE.x
	var other: float = float(pair_x[1 - k])
	share = clampf(share, 0.05, other - 0.04) if k == 0 else clampf(share, other + 0.04, 0.95)
	pair_x[k] = snappedf(share, 0.005)
	_pair_store()
	_log("hero", "пара: %s встал на %.2f (расстояние %.2f)" % ["левый" if k == 0 else "правый", share, float(pair_x[1]) - float(pair_x[0])])
	_reload()


## The ⇆ handles take the mouse first (in both modes): true when they did.
func _stand_mouse(event: InputEvent, m: Vector2) -> bool:
	if row != "pair":
		return false
	if event is InputEventMouseMotion and _stand_drag >= 0:
		_stand_at = m.x
		return true
	if event is InputEventMouseButton and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		if (event as InputEventMouseButton).pressed:
			for k in 2:
				if _stand_point(k).distance_to(m) < REACH:
					_stand_drag = k
					_stand_at = m.x
					return true
		elif _stand_drag >= 0:
			var k2 := _stand_drag
			_stand_drag = -1
			_stand_to(k2, _stand_at)
			return true
	return false


func _draw_stands(canvas: Node2D) -> void:
	if row != "pair":
		return
	var font := ThemeDB.fallback_font
	for k in 2:
		var at := _stand_point(k)
		if not is_finite(at.x):
			continue
		if _stand_drag == k:                     # (where it will stand: a line from the floor up)
			canvas.draw_line(Vector2(_stand_at, floor_y - 40.0), Vector2(_stand_at, floor_y + 22.0), C_CHOSEN, 3.0, true)
			at.x = _stand_at
		canvas.draw_rect(Rect2(at - Vector2(30, 15), Vector2(60, 30)), C_CHOSEN if _stand_drag == k else C_INK, true)
		canvas.draw_string(font, at + Vector2(-30, 8), "⇆", HORIZONTAL_ALIGNMENT_CENTER, 60, 24, Color.WHITE)


## A pair: the left (0) or the right (1) hero.
func _pair_actor(k: int) -> Actor:
	return actors.get(hero_id if k == 0 else partner_id, null)


## A pair: that one's pose (at rest, if it has none yet).
func _pose_for(k: int) -> Dictionary:
	if (pair_pose[k] as Dictionary).is_empty():
		pair_pose[k] = rest_pose(_pair_actor(k))
	return pair_pose[k]


## A pair: what the dots changed goes back to the edited hero's pose.
func _pair_store() -> void:
	if row == "pair":
		pair_pose[pair_edit] = pose_now


## A pair: the other hero's pose is the one the dots change now.
func _pick_edit(k: int) -> void:
	if row != "pair" or k == pair_edit:
		return
	_pair_store()
	pair_edit = k
	pose_now = _pose_for(k)
	_drag = ""
	_hover = ""
	_show_front()
	_show_edit()
	_dirty_state = true
	_say("Правите позу: %s. Точки — на нём." % str(_hero_def(hero_id if k == 0 else partner_id).get("title", "")))


var _edit_seg: HBoxContainer


func _show_edit() -> void:
	if _edit_seg == null:
		return
	for b: Button in _edit_seg.get_children():
		b.set_pressed_no_signal(b.get_index() == pair_edit)


## The hero the dots and the faults are about: the chosen one, or the first of the row.
func _main() -> Actor:
	if actors.has(hero_id):
		return actors[hero_id]
	return actors.values()[0] if not actors.is_empty() else null


## How complete the hero is: a bar with the percent, and a list of what it has and what it lacks.
func _ready_box(ready: Dictionary) -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 12)
	var l := Label.new()
	l.text = "Готовность"
	l.custom_minimum_size = Vector2(120, 0)
	line.add_child(l)
	var bar := ProgressBar.new()
	bar.min_value = 0
	bar.max_value = 100
	bar.value = float(ready.get("percent", 0))
	bar.show_percentage = false
	bar.custom_minimum_size = Vector2(0, 14)
	bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	bar.add_theme_stylebox_override("background", _box(C_CONTROL, 7, 0, 0))
	bar.add_theme_stylebox_override("fill", _box(C_CHOSEN, 7, 0, 0))
	line.add_child(bar)
	var pc := Label.new()
	pc.text = "%d%%" % int(bar.value)
	pc.custom_minimum_size = Vector2(56, 0)
	pc.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	line.add_child(pc)
	var list := VBoxContainer.new()
	list.add_theme_constant_override("separation", 2)
	list.visible = false
	var more := _toggle("Что есть и чего нет", false, func(on: bool) -> void: list.visible = on)
	more.theme_type_variation = "Tile"
	line.add_child(more)
	box.add_child(line)
	for it: Dictionary in ready.get("items", []):
		var r := HBoxContainer.new()
		r.add_theme_constant_override("separation", 10)
		var mark := Label.new()
		mark.text = "✓" if it["ok"] else "✕"
		mark.custom_minimum_size = Vector2(24, 0)
		mark.add_theme_color_override("font_color", C_CHOSEN if it["ok"] else C_MAIN)
		r.add_child(mark)
		var t := Label.new()
		t.text = "%s — %s" % [it["title"], it["say"]]
		t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		t.add_theme_font_size_override("font_size", 17)
		r.add_child(t)
		list.add_child(r)
	box.add_child(list)
	return box


## Why an action will not play right in this window for this hero ("" when it will): it needs a partner, a thing
## to hold (the workshop puts no things on the stage yet), or the hero's own check found it faulty.
func _why_not(id: String) -> String:
	var a: Dictionary = actions().get(id, {})
	if (a.get("group", "") == "two" or a.has("pair") or a.get("partner_only", false)) and (cfg.get("heroes", []) as Array).size() < 2:
		return "Для двоих: в рубрике один герой, играть не с кем."
	if (id in ["give", "receive"]) and (cfg.get("heroes", []) as Array).size() < 2:
		return "Из рук в руки: в рубрике один герой, передавать некому."
	if (_hero_def(hero_id).get("ready", {}).get("bad", []) as Array).has(id):
		return "У этого героя с браком: проверка нашла ошибки (нажмите — покажу какие)."
	return ""


func _hero_count() -> int:
	if row == "one":
		return 1
	return (cfg.get("proof", []) if row == "proof" else cfg.get("heroes", [])).size()


## The views a hero has drawn: front always; side (left and right) and back when puppet/side, puppet/back exist.
static func _views_of(h: Dictionary) -> Array:
	var d: String = str(h.get("dir", ""))
	var out: Array = ["front"]
	if d != "" and FileAccess.file_exists(d.path_join("side/rig.json")):
		out.append_array(["left", "right"])
	if d != "" and FileAccess.file_exists(d.path_join("back/rig.json")):
		out.append("back")
	return out


## A pair in words: «пара: «А» слева, «Б» справа».
func _pair_words() -> String:
	return "пара: «%s» слева, «%s» справа" % [str(_hero_def(hero_id).get("title", hero_id)), str(_hero_def(partner_id).get("title", partner_id))]


func _hero_def(id: String) -> Dictionary:
	for h: Dictionary in cfg.get("heroes", []) + cfg.get("proof", []):
		if h["id"] == id:
			return h
	return {}


# ----------------------------------------------------------------------------- the clock

func _physics_process(delta: float) -> void:
	if paused:
		while _steps_wanted > 0:
			_steps_wanted -= 1
			_one_step(delta)
		return
	_acc += speed
	while _acc >= 1.0:
		_acc -= 1.0
		_one_step(delta)


func _one_step(delta: float) -> void:
	if still:
		_set_life()                      # (a turn makes the hero's motion anew)
	super._physics_process(delta)
	if not _pending.is_empty():
		var calm := true
		for a: Actor in actors.values():
			calm = calm and not a.motion.busy()
		if calm:
			var line: Dictionary = _pending
			_pending = {}
			_command(line)
	var a := _main()
	if a != null and _trails:
		for h: String in ["hand_l", "hand_r", "foot_l", "foot_r"]:
			var tr: Array = _trail.get_or_add(h, [])
			tr.append(a.puppet.handle_position(h))
			if tr.size() > TRAIL:
				tr.pop_front()
	if _loop and tab == 0 and chosen != "" and _pending.is_empty():
		var busy := false
		for b: Actor in actors.values():
			busy = busy or b.motion.busy()
		_idle = 0 if busy else _idle + 1
		if _idle == 40:
			_play(chosen)


func _process(delta: float) -> void:
	super._process(delta)
	# (a control never shrinks by itself: once its content was laid out narrow it stayed too tall, cut at the
	# bottom; it is held at the window's size, the action list scrolls inside)
	if _panel_bg != null and _panel_bg.size != _panel_want:
		_panel_bg.size = _panel_want
	if _dots != null:
		_dots.queue_redraw()
	_poll += delta
	if _poll >= 0.4:
		_poll = 0.0
		_watch_files()
		_refresh_playing()
		if _dirty_state:
			_write_state()
	_scripted()


func _set_paused(on: bool) -> void:
	paused = on
	if _pause_btn != null:
		_pause_btn.text = "▶  Пуск" if paused else "❚❚  Пауза"


# ----------------------------------------------------------------------------- the look

static func _box(colour: Color, radius := 10, h := 14, v := 8) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = colour
	sb.set_corner_radius_all(radius)
	sb.content_margin_left = h
	sb.content_margin_right = h
	sb.content_margin_top = v
	sb.content_margin_bottom = v
	return sb


## One theme for every control: every state set (a chosen tile under the mouse stays readable).
func _theme() -> Theme:
	var t := Theme.new()
	t.default_font_size = 21
	var clear := _box(Color(0, 0, 0, 0))
	# a plain button / a tile / a segment: stone at rest, deep blue when chosen (toggle), white text on blue
	for kind: String in ["Button"]:
		t.set_stylebox("normal", kind, _box(C_CONTROL))
		t.set_stylebox("hover", kind, _box(C_HOVER))
		t.set_stylebox("pressed", kind, _box(C_CHOSEN))
		t.set_stylebox("hover_pressed", kind, _box(C_CHOSEN_HOVER))
		t.set_stylebox("disabled", kind, _box(C_CONTROL))
		t.set_stylebox("focus", kind, clear)
		t.set_color("font_color", kind, C_INK)
		t.set_color("font_hover_color", kind, C_INK)
		t.set_color("font_focus_color", kind, C_INK)
		t.set_color("font_pressed_color", kind, Color.WHITE)
		t.set_color("font_hover_pressed_color", kind, Color.WHITE)
		t.set_color("font_disabled_color", kind, C_SOFT)
	# the main button: red, white text
	t.set_type_variation("Main", "Button")
	t.set_stylebox("normal", "Main", _box(C_MAIN, 10, 18, 10))
	t.set_stylebox("hover", "Main", _box(C_MAIN_HOVER, 10, 18, 10))
	t.set_stylebox("pressed", "Main", _box(C_MAIN_HOVER, 10, 18, 10))
	t.set_stylebox("hover_pressed", "Main", _box(C_MAIN_HOVER, 10, 18, 10))
	for c: String in ["font_color", "font_hover_color", "font_pressed_color", "font_hover_pressed_color", "font_focus_color"]:
		t.set_color(c, "Main", Color.WHITE)
	# a tile of an action: smaller, a little round
	t.set_type_variation("Tile", "Button")
	t.set_stylebox("normal", "Tile", _box(C_CONTROL, 8, 12, 7))
	t.set_stylebox("hover", "Tile", _box(C_HOVER, 8, 12, 7))
	t.set_stylebox("pressed", "Tile", _box(C_CHOSEN, 8, 12, 7))
	t.set_stylebox("hover_pressed", "Tile", _box(C_CHOSEN_HOVER, 8, 12, 7))
	t.set_font_size("font_size", "Tile", 19)
	# an action that will not play right here: a quieter tile (light card, soft text), still pressable
	t.set_type_variation("Off", "Button")
	t.set_stylebox("normal", "Off", _box(C_CARD, 8, 12, 7))
	t.set_stylebox("hover", "Off", _box(C_HOVER, 8, 12, 7))
	t.set_stylebox("pressed", "Off", _box(C_CHOSEN, 8, 12, 7))
	t.set_stylebox("hover_pressed", "Off", _box(C_CHOSEN_HOVER, 8, 12, 7))
	t.set_color("font_color", "Off", C_SOFT)
	t.set_color("font_hover_color", "Off", C_INK)
	t.set_font_size("font_size", "Off", 19)
	# the two modes on top: big, the chosen one blue
	t.set_type_variation("Mode", "Button")
	for st: String in ["normal", "hover", "pressed", "hover_pressed"]:
		var col: Color = {"normal": C_CONTROL, "hover": C_HOVER, "pressed": C_CHOSEN, "hover_pressed": C_CHOSEN_HOVER}[st]
		t.set_stylebox(st, "Mode", _box(col, 12, 16, 14))
	t.set_font_size("font_size", "Mode", 22)
	# fields: filled, no border; focus keeps the colour, a red line inside (the site's rule)
	var field := _box(C_CONTROL, 10, 14, 9)
	var focus := _box(C_CONTROL, 10, 14, 9)
	focus.border_color = C_MAIN
	focus.set_border_width_all(2)
	t.set_stylebox("normal", "LineEdit", field)
	t.set_stylebox("focus", "LineEdit", focus)
	t.set_color("font_color", "LineEdit", C_INK)
	t.set_color("font_placeholder_color", "LineEdit", C_SOFT)
	t.set_color("caret_color", "LineEdit", C_MAIN)
	t.set_color("selection_color", "LineEdit", Color(C_CHOSEN, 0.25))
	t.set_color("font_color", "Label", C_INK)
	# sliders: a stone track, a blue grabber area
	t.set_stylebox("slider", "HSlider", _box(C_CONTROL, 4, 0, 3))
	t.set_stylebox("grabber_area", "HSlider", _box(C_CHOSEN, 4, 0, 3))
	t.set_stylebox("grabber_area_highlight", "HSlider", _box(C_CHOSEN_HOVER, 4, 0, 3))
	t.set_stylebox("panel", "PanelContainer", _box(C_CARD, 14, 18, 14))
	t.set_type_variation("Fault", "PanelContainer")
	t.set_stylebox("panel", "Fault", _box(C_FAULT_BG, 12, 16, 12))
	t.set_type_variation("Picked", "PanelContainer")
	var picked := _box(C_CARD, 14, 18, 14)
	picked.border_color = C_CHOSEN
	picked.set_border_width_all(3)
	t.set_stylebox("panel", "Picked", picked)
	t.set_stylebox("panel", "ScrollContainer", clear)
	for part: String in ["scroll", "scroll_focus"]:
		t.set_stylebox(part, "VScrollBar", _box(Color(0, 0, 0, 0), 4, 0, 0))
	t.set_stylebox("grabber", "VScrollBar", _box(C_HOVER, 4, 4, 4))
	t.set_stylebox("grabber_highlight", "VScrollBar", _box(C_SOFT, 4, 4, 4))
	t.set_stylebox("grabber_pressed", "VScrollBar", _box(C_SOFT, 4, 4, 4))
	return t


func _title(text: String, size := 30) -> Label:
	var l := Label.new()
	l.text = text
	if _head_font != null:
		l.add_theme_font_override("font", _head_font)
	l.add_theme_font_size_override("font_size", size)
	return l


func _note(text: String, size := 18) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", C_SOFT)
	l.add_theme_font_size_override("font_size", size)
	return l


func _btn(text: String, on_press: Callable, variation := "") -> Button:
	var b := Button.new()
	b.text = text
	b.theme_type_variation = variation
	b.focus_mode = Control.FOCUS_NONE
	b.pressed.connect(on_press)
	return b


func _toggle(text: String, on: bool, on_toggle: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.toggle_mode = true
	b.button_pressed = on
	b.focus_mode = Control.FOCUS_NONE
	b.toggled.connect(on_toggle)
	return b


## A segmented choice: one of `options` ([label, value]) is chosen.
func _seg(options: Array, current: Variant, on_pick: Callable, variation := "") -> HBoxContainer:
	var box := HBoxContainer.new()
	box.add_theme_constant_override("separation", 4)
	var group := ButtonGroup.new()
	for o: Array in options:
		var b := Button.new()
		b.text = o[0]
		b.toggle_mode = true
		b.button_group = group
		b.theme_type_variation = variation
		b.focus_mode = Control.FOCUS_NONE
		b.button_pressed = o[1] == current
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.pressed.connect(func() -> void: on_pick.call(o[1]))
		box.add_child(b)
	return box


func _line(title: String, control: Control) -> HBoxContainer:
	var r := HBoxContainer.new()
	r.add_theme_constant_override("separation", 12)
	var l := Label.new()
	l.text = title
	l.custom_minimum_size = Vector2(120, 0)
	r.add_child(l)
	control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	r.add_child(control)
	return r


func _slider(lo: float, hi: float, value: float, fmt: String, on_change: Callable, on_done := Callable()) -> HBoxContainer:
	var r := HBoxContainer.new()
	r.add_theme_constant_override("separation", 12)
	var s := HSlider.new()
	s.min_value = lo
	s.max_value = hi
	s.step = 0.05
	s.value = value
	s.focus_mode = Control.FOCUS_NONE
	s.custom_minimum_size = Vector2(0, 32)
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	s.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var v := Label.new()
	v.text = fmt % value
	v.custom_minimum_size = Vector2(64, 0)
	v.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	s.value_changed.connect(func(x: float) -> void:
		v.text = fmt % x
		on_change.call(x))
	if on_done.is_valid():
		s.drag_ended.connect(func(changed: bool) -> void:
			if changed:
				on_done.call())
	r.add_child(s)
	r.add_child(v)
	return r


func _gap(h := 6) -> Control:
	var c := Control.new()
	c.custom_minimum_size = Vector2(0, h)
	return c


# ----------------------------------------------------------------------------- the panel

## The panel takes everything right of the stage, the whole height (the window is resizable).
func _fit_panel() -> void:
	if _panel_bg == null or not is_instance_valid(_panel_bg):
		return
	var vs := get_viewport().get_visible_rect().size
	_panel_want = Vector2(maxf(PANEL_W, vs.x - SIZE.x), maxf(SIZE.y, vs.y))
	_panel_bg.size = _panel_want
	if _below != null and is_instance_valid(_below):
		_below.position = Vector2(0, SIZE.y)
		_below.size = Vector2(SIZE.x, maxf(0.0, vs.y - SIZE.y))


func _build_panel() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 20
	add_child(layer)
	var bg := PanelContainer.new()
	bg.position = Vector2(SIZE.x, 0)
	bg.size = Vector2(PANEL_W, SIZE.y)
	_panel_bg = bg
	_fit_panel()
	if not get_viewport().size_changed.is_connected(_fit_panel):
		get_viewport().size_changed.connect(_fit_panel)
	bg.theme = _theme()
	bg.add_theme_stylebox_override("panel", _box(C_PAPER, 0, 28, 24))
	layer.add_child(bg)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 14)
	bg.add_child(col)

	# the rubric: whose heroes, actions and poses these are (never mixed: one rubric at a time)
	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 12)
	var head := VBoxContainer.new()
	head.add_theme_constant_override("separation", 0)
	head.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(_note("Мастерская" + (" · общая библиотека" if cfg.get("core", false) else "") + " · рубрика", 18))
	var wt := str(cfg.get("world_title", ""))
	var name := _title("«%s»" % wt if wt != "" else "Рубрика не выбрана", 32)
	name.clip_text = true
	head.add_child(name)
	top.add_child(head)
	var worlds: Array = cfg.get("worlds", [])
	var box := HFlowContainer.new()
	box.add_theme_constant_override("h_separation", 6)
	box.add_theme_constant_override("v_separation", 6)
	box.visible = false
	if worlds.size() > 1 or (worlds.size() == 1 and str(worlds[0]["root"]) != str(cfg.get("world", ""))):
		var change := _toggle("Сменить рубрику", false, func(on: bool) -> void: box.visible = on)
		change.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		top.add_child(change)
		var group := ButtonGroup.new()
		for w: Dictionary in worlds:
			var b := Button.new()
			b.text = "%s  · %d" % [str(w["title"]), (w.get("heroes", []) as Array).size()]
			b.tooltip_text = "%s\nгероев: %d" % [str(w["root"]), (w.get("heroes", []) as Array).size()]
			b.theme_type_variation = "Tile"
			b.toggle_mode = true
			b.button_group = group
			b.focus_mode = Control.FOCUS_NONE
			b.button_pressed = str(w["root"]) == str(cfg.get("world", ""))
			b.pressed.connect(func() -> void: _switch_world(w))
			box.add_child(b)
	col.add_child(top)
	col.add_child(box)
	var rows: Array = [["Один герой", "one"], ["Все герои", "all"], ["Пробные тела", "proof"]]
	if _pair_pool().size() >= 2:
		rows.append(["Пара", "pair"])
	col.add_child(_seg(rows, row, func(v: String) -> void:
		row = v
		_reload()))
	if row == "one":
		var heroes := HFlowContainer.new()
		heroes.add_theme_constant_override("h_separation", 6)
		heroes.add_theme_constant_override("v_separation", 6)
		var group := ButtonGroup.new()
		var list: Array = cfg.get("heroes", [])
		if list.is_empty() or str(hero_id).begins_with("proof:"):
			list = list + cfg.get("proof", [])
		for h: Dictionary in list:
			var b := Button.new()
			b.text = str(h.get("title", h["id"])).replace("проба: ", "")
			b.theme_type_variation = "Tile"
			b.toggle_mode = true
			b.button_group = group
			b.focus_mode = Control.FOCUS_NONE
			b.button_pressed = h["id"] == hero_id
			if str(h["id"]).begins_with("proof:"):
				b.tooltip_text = "пробное тело: " + str(h["id"]).trim_prefix("proof:")
			b.pressed.connect(func() -> void:
				hero_id = h["id"]
				_reload())
			heroes.add_child(b)
		col.add_child(heroes)
		var ready: Dictionary = _hero_def(hero_id).get("ready", {})
		if not ready.is_empty():
			col.add_child(_ready_box(ready))
	elif row == "pair":
		# two heroes side by side: who stands on the left (and leads), who on the right, how far apart
		for k in 2:
			var flow := HFlowContainer.new()
			flow.add_theme_constant_override("h_separation", 6)
			flow.add_theme_constant_override("v_separation", 6)
			var group2 := ButtonGroup.new()
			for h: Dictionary in _pair_pool():
				var hid: String = h["id"]
				var b := Button.new()
				b.text = str(h.get("title", hid)).replace("проба: ", "")
				b.theme_type_variation = "Tile"
				b.toggle_mode = true
				b.button_group = group2
				b.focus_mode = Control.FOCUS_NONE
				b.button_pressed = hid == (hero_id if k == 0 else partner_id)
				b.pressed.connect(func() -> void:
					_pair_store()
					if k == 0:
						if hid == partner_id:
							partner_id = hero_id
							pair_pose.reverse()
						hero_id = hid
					else:
						if hid == hero_id:
							hero_id = partner_id
							pair_pose.reverse()
						partner_id = hid
					_reload())
				flow.add_child(b)
			col.add_child(_line("Слева" if k == 0 else "Справа", flow))
		var dist := _slider(0.05, 0.7, float(pair_x[1]) - float(pair_x[0]), "%.2f", func(x: float) -> void: _set_pair_dx(x), func() -> void:
			_pair_store()
			_log("hero", "пара: расстояние %.2f" % (float(pair_x[1]) - float(pair_x[0])))
			_reload())
		(dist.get_child(0) as HSlider).step = 0.01
		dist.tooltip_text = "как далеко они стоят: доля ширины сцены (или тяните героя за ⇆ под ногами)"
		col.add_child(_line("Расстояние", dist))
		col.add_child(_note("Героя можно тащить вбок за ⇆ у его ног.", 16))
	elif row == "proof":
		# which proof bodies stand side by side: at most four, so they do not crowd into a mess
		var picks := HFlowContainer.new()
		picks.add_theme_constant_override("h_separation", 6)
		picks.add_theme_constant_override("v_separation", 6)
		for h: Dictionary in cfg.get("proof", []):
			var id: String = h["id"]
			var b := Button.new()
			b.text = str(h.get("title", id)).replace("проба: ", "")
			b.theme_type_variation = "Tile"
			b.toggle_mode = true
			b.focus_mode = Control.FOCUS_NONE
			b.button_pressed = proof_pick.has(id)
			b.pressed.connect(func() -> void:
				if proof_pick.has(id):
					if proof_pick.size() > 1:
						proof_pick.erase(id)
				else:
					proof_pick.append(id)
					if proof_pick.size() > PROOF_MAX:
						proof_pick.pop_front()
				_reload())
			picks.add_child(b)
		col.add_child(picks)
		col.add_child(_note("Рядом стоят до четырёх тел: отметьте, какие сравнить.", 16))
	# the views: only the ones the hero has drawn can be pressed (ours face the audience: front only, as a rule)
	var has := _views_of(_hero_def(hero_id))
	var vseg := _seg([["Спереди", "front"], ["Влево", "left"], ["Вправо", "right"], ["Сзади", "back"]], "front",
		func(v: String) -> void:
			for id: String in actors:
				_command({"who": id, "turn": v}))
	for b: Button in vseg.get_children():
		var v: String = ["front", "left", "right", "back"][b.get_index()]
		b.disabled = not has.has(v)
		b.tooltip_text = "" if has.has(v) else "Этот вид у героя не нарисован"
	col.add_child(_line("Вид", vseg))
	if has.size() == 1:
		col.add_child(_note("Нарисован только вид спереди: наши герои смотрят на зрителя.", 16))

	# the two modes
	var modes := HBoxContainer.new()
	modes.add_theme_constant_override("separation", 8)
	for i in 2:
		var b := Button.new()
		b.text = ["Смотреть действия", "Новое действие из поз"][i]
		b.theme_type_variation = "Mode"
		b.toggle_mode = true
		b.focus_mode = Control.FOCUS_NONE
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.pressed.connect(func() -> void: _show_mode(i))
		modes.add_child(b)
		_modes.append(b)
	var logb := _toggle("Журнал", _log_open, func(on: bool) -> void:
		_log_open = on
		if _log_card != null:
			_log_card.visible = on
			_fill_log())
	logb.theme_type_variation = "Mode"
	logb.tooltip_text = "что было в окне: действия, брак, позы, команды ИИ — любую строку или всё можно скопировать для ИИ"
	modes.add_child(logb)
	col.add_child(_gap(4))
	col.add_child(modes)
	_status = _note("", 19)
	col.add_child(_status)
	var pages := Control.new()
	pages.size_flags_vertical = Control.SIZE_EXPAND_FILL
	col.add_child(pages)
	for page: Control in [_actions_page(), _poses_page()]:
		page.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		pages.add_child(page)
		_pages.append(page)
	col.add_child(_log_panel())


## Another rubric: its heroes, its actions, its poses (each rubric keeps its own .tadam/workshop).
func _switch_world(w: Dictionary) -> void:
	_save_poses()
	for k: String in ["heroes", "state_dir", "actions_dir", "save_dir"]:
		cfg[k] = w[k]
	cfg["world"] = w["root"]
	cfg["world_title"] = w["title"]
	world_actions_dir = str(w["actions_dir"])
	_actions.clear()
	var hs: Array = w.get("heroes", [])
	hero_id = str(hs[0]["id"]) if not hs.is_empty() else ""
	row = "one"
	poses = []
	pose_now = {}
	chosen = ""
	_cmd_seen = 0
	_load_poses()
	get_tree().reload_current_scene()


func _show_mode(i: int) -> void:
	tab = i
	for k in _modes.size():
		(_modes[k] as Button).set_pressed_no_signal(k == i)
		(_pages[k] as Control).visible = k == i
	_dirty_state = true
	if i == 1:
		_say("Тяните точки на герое. Поза нравится — «Запомнить позу» или клавиша F.")
		_apply_pose()
	else:
		_say("Нажмите действие: герой сыграет его из покоя.")
		_rest(false)


func _actions_page() -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 12)
	_search = LineEdit.new()
	_search.placeholder_text = "Найти действие: «помахать», wave…"
	_search.clear_button_enabled = true
	_search.text_changed.connect(func(_t: String) -> void: _fill_tiles())
	box.add_child(_search)
	# 1. the actions: the first thing to press
	var step := _note("Нажмите любое действие — герой сыграет его. Потом под списком можно выбрать руку, локоть, силу и темп.", 16)
	step.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_how_hint = step
	box.add_child(step)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.custom_minimum_size = Vector2(0, 200)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_tiles_scroll = scroll
	_tiles = VBoxContainer.new()
	_tiles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_tiles.add_theme_constant_override("separation", 6)
	scroll.add_child(_tiles)
	box.add_child(scroll)
	_fill_tiles()


	# 2. how to play the chosen one: shown only once an action is chosen, under the list
	var how := PanelContainer.new()
	_how_card = how
	var hv := VBoxContainer.new()
	hv.add_theme_constant_override("separation", 8)
	how.add_child(hv)
	_how_title = _title("", 22)
	_how_title.clip_text = true
	hv.add_child(_how_title)
	_how_note = _note("", 16)
	_how_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hv.add_child(_how_note)
	_side_row = _line("Рука", _seg([["Правая", "right"], ["Левая", "left"], ["Обе", "both"]], _side, _pick_side))
	hv.add_child(_side_row)
	_elbow_seg = _seg([["Сам", ""], ["Вниз", "down"], ["Вверх", "up"], ["Наружу", "out"], ["Внутрь", "in"]], _elbow_say, _pick_elbow)
	_elbow_row = _line("Локоть", _elbow_seg)
	hv.add_child(_elbow_row)
	var sliders := HBoxContainer.new()
	sliders.add_theme_constant_override("separation", 18)
	for s: Array in [["Сила", _energy, func(v: float) -> void: _energy = v], ["Темп", _speed, func(v: float) -> void: _speed = v]]:
		var one := HBoxContainer.new()
		one.add_theme_constant_override("separation", 10)
		var l := Label.new()
		l.text = s[0]
		one.add_child(l)
		var sl := _slider(0.5, 1.6, s[1], "%.1f×", s[2], _replay)
		sl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		one.add_child(sl)
		one.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		sliders.add_child(one)
	hv.add_child(sliders)
	var orow := HBoxContainer.new()
	orow.add_theme_constant_override("separation", 8)
	var over := _toggle("Следующее — поверх этого", _over_mode, func(on: bool) -> void: _over_mode = on)
	over.tooltip_text = "Обычно перед новым действием герой возвращается в покой. Включите, чтобы следующее действие легло поверх этого: например, махать на ходу."
	over.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	orow.add_child(over)
	orow.add_child(_btn("В покой", func() -> void: _rest(true)))
	hv.add_child(orow)

	# what plays now, and the faults of the chosen action
	var prow := HBoxContainer.new()
	prow.add_theme_constant_override("separation", 12)
	var pl := Label.new()
	pl.text = "Играет:"
	prow.add_child(pl)
	_playing_box = HFlowContainer.new()
	_playing_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_playing_box.add_theme_constant_override("h_separation", 6)
	prow.add_child(_playing_box)
	box.add_child(prow)
	box.add_child(_how_card)
	_faults = PanelContainer.new()
	_faults.theme_type_variation = "Fault"
	_faults_text = Label.new()
	_faults_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_faults_text.add_theme_font_size_override("font_size", 16)
	_faults.add_child(_faults_text)
	_faults.visible = false
	box.add_child(_faults)
	_update_how()
	return box


func _fill_tiles() -> void:
	if _tiles == null:
		return
	for c in _tiles.get_children():
		c.queue_free()
	_tile_of.clear()
	var q := _search.text.strip_edges().to_lower() if _search != null else ""
	var by_group := {}
	for id: String in actions():
		var a: Dictionary = actions()[id]
		if id.begins_with("_") or id == "rest":
			continue
		var title := _title_of(a, id)
		if q != "" and not (q in id.to_lower() or q in title.to_lower()):
			continue
		by_group.get_or_add(a.get("group", "other"), []).append(id)
	var own: Array = world_action_ids.filter(func(id: String) -> bool: return by_group.values().any(func(l: Array) -> bool: return l.has(id)))
	var order: Array = ["_own"] + GROUP_TITLES.keys() + by_group.keys().filter(func(k: String) -> bool: return not GROUP_TITLES.has(k))
	var any := false
	var off := {}                        # reason -> the actions that will not play right here for it
	for g: String in order:
		var ids: Array = own if g == "_own" else by_group.get(g, []).filter(func(id: String) -> bool: return not world_action_ids.has(id))
		ids = ids.filter(func(id: String) -> bool:
			var why := _why_not(id)
			if why != "":
				off.get_or_add(why, []).append(id)
			return why == "")
		if ids.is_empty():
			continue
		any = true
		ids.sort()
		var head := _title("Действия этой рубрики" if g == "_own" else GROUP_TITLES.get(g, g), 21)
		head.add_theme_color_override("font_color", C_MAIN if g == "_own" else C_INK)
		_tiles.add_child(head)
		var flow := HFlowContainer.new()
		flow.add_theme_constant_override("h_separation", 6)
		flow.add_theme_constant_override("v_separation", 6)
		for id: String in ids:
			var b := Button.new()
			b.text = _title_of(actions()[id], id)
			b.tooltip_text = id
			b.theme_type_variation = "Tile"
			b.toggle_mode = true
			b.focus_mode = Control.FOCUS_NONE
			b.button_pressed = id == chosen
			b.pressed.connect(func() -> void: _pick_action(id))
			flow.add_child(b)
			_tile_of[id] = b
		_tiles.add_child(flow)
		_tiles.add_child(_gap(4))
	if not off.is_empty():
		any = true
		_tiles.add_child(_title("Здесь не сыграет как надо", 21))
		for why: String in off:
			_tiles.add_child(_note(why, 16))
			var flow2 := HFlowContainer.new()
			flow2.add_theme_constant_override("h_separation", 6)
			flow2.add_theme_constant_override("v_separation", 6)
			var l2: Array = off[why]
			l2.sort()
			for id: String in l2:
				var b := Button.new()
				b.text = _title_of(actions()[id], id)
				b.tooltip_text = "%s: %s" % [id, why]
				b.theme_type_variation = "Off"
				b.toggle_mode = true
				b.focus_mode = Control.FOCUS_NONE
				b.button_pressed = id == chosen
				b.pressed.connect(func() -> void: _pick_action(id))
				flow2.add_child(b)
				_tile_of[id] = b
			_tiles.add_child(flow2)
			_tiles.add_child(_gap(4))
	if not any:
		_tiles.add_child(_note("Ничего не нашлось. Имя действия латиницей или его название по-русски."))


func _mark_tile(id: String) -> void:
	for k: String in _tile_of:
		(_tile_of[k] as Button).set_pressed_no_signal(k == id)
	if _tile_of.has(id) and _tiles_scroll != null:      # (the card opens under the list: keep the tile in sight)
		var t: Control = _tile_of[id]
		await get_tree().process_frame
		await get_tree().process_frame
		if is_instance_valid(t) and is_instance_valid(_tiles_scroll):
			_tiles_scroll.ensure_control_visible(t)


static func _title_of(a: Dictionary, id: String) -> String:
	var t: Variant = a.get("title", id)
	if t is Dictionary:
		return str(t.get("ru", t.get("en", id)))
	return str(t)


func _poses_page() -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 12)
	box.add_child(_note("Синие точки — кисти и стопы, красные — таз, плечи (наклон) и макушка. На кисти: правый клик — ладонь, кулак, ребро, палец; колесо — поворот; Shift + правый клик — локоть.", 18))
	if row == "pair":
		_edit_seg = _seg([[str(_hero_def(hero_id).get("title", hero_id)) + " (слева)", 0], [str(_hero_def(partner_id).get("title", partner_id)) + " (справа)", 1]],
			pair_edit, func(k: int) -> void: _pick_edit(k), "Tile")
		box.add_child(_line("Правлю позу", _edit_seg))
		box.add_child(_note("«Запомнить позу» запоминает обоих сразу: в каждой карточке — поза левого и правого.", 16))
	var actions_row := HBoxContainer.new()
	actions_row.add_theme_constant_override("separation", 8)
	var fix := _btn("Запомнить позу  (F)", _fix, "Main")
	fix.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	actions_row.add_child(fix)
	actions_row.add_child(_btn("Показать движение", _play_poses))
	actions_row.add_child(_btn("В покой", func() -> void:
		pose_now = rest_pose(_edited())
		if row == "pair":
			pair_pose = [rest_pose(_pair_actor(0)), rest_pose(_pair_actor(1))]
			pose_now = pair_pose[pair_edit]
		_sel = -1
		_fill_poses()
		_apply_pose()))
	box.add_child(actions_row)
	# which arm is drawn over the other (a hand raised across the body, over the other arm)
	var fr := "r" if bool(pose_now.get("arm_r", {}).get("front", false)) else ("l" if bool(pose_now.get("arm_l", {}).get("front", false)) else "")
	_front_seg = _seg([["Как нарисовано", ""], ["Правая", "r"], ["Левая", "l"]], fr, func(v: String) -> void:
		for ch: String in ["arm_l", "arm_r"]:
			if pose_now.get(ch, null) is Dictionary:
				if ch.right(1) == v:
					pose_now[ch]["front"] = true
				else:
					pose_now[ch].erase("front")
		_apply_pose()
		_say("Спереди: %s." % {"": "как нарисовано", "r": "правая рука", "l": "левая рука"}[v]), "Tile")
	box.add_child(_line("Спереди", _front_seg))
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_pose_cards = VBoxContainer.new()
	_pose_cards.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_pose_cards.add_theme_constant_override("separation", 8)
	scroll.add_child(_pose_cards)
	box.add_child(scroll)
	var sv := VBoxContainer.new()
	sv.add_theme_constant_override("separation", 8)
	sv.add_child(_title("Сохранить как действие " + ("общей библиотеки" if cfg.get("core", false) else "рубрики"), 21))
	_save_id = LineEdit.new()
	_save_id.placeholder_text = "имя латиницей: salute"
	_save_title = LineEdit.new()
	_save_title.placeholder_text = "название: отдать честь"
	var srow := HBoxContainer.new()
	srow.add_theme_constant_override("separation", 8)
	_save_id.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_save_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_save_id.custom_minimum_size = Vector2(120, 0)
	_save_title.custom_minimum_size = Vector2(120, 0)
	srow.add_child(_save_id)
	srow.add_child(_save_title)
	srow.add_child(_btn("Сохранить", _save_action, "Main"))
	sv.add_child(srow)
	box.add_child(sv)
	_fill_poses()
	return box


## What a pose changes against rest, in words (the card's title).
func _pose_words(p: Dictionary) -> String:
	var r := rest_pose()
	var w: Array = []
	for ch: String in ["arm_r", "arm_l"]:
		var arm0: Dictionary = p.get(ch, {})
		if arm0.has("raise"):                   # (in angles: a hand hanging as at rest is not news)
			if float(arm0["raise"]) < 15.0 and absf(float(arm0.get("elbow", 0.0))) < 12.0 and not arm0.has("look"):
				continue
			w.append("%s: подъём %d°, локоть %d°" % ["правая рука" if ch == "arm_r" else "левая рука", int(arm0["raise"]), int(arm0.get("elbow", 0.0))])
			continue
		if JSON.stringify(p.get(ch, {})) != JSON.stringify(r.get(ch, {})):
			var arm: Dictionary = p.get(ch, {})
			var extra: Array = []
			if arm.has("look"):
				extra.append(LOOK_NAMES.get(arm["look"], arm["look"]))
			if arm.get("elbow", null) is String:
				extra.append(ELBOW_NAMES.get(arm["elbow"], arm["elbow"]))
			w.append(("правая рука" if ch == "arm_r" else "левая рука") + (" (" + ", ".join(extra) + ")" if not extra.is_empty() else ""))
	var lg: Dictionary = p.get("legs", {})
	if float(lg.get("drop", 0.0)) > 0.01:
		w.append("присел")
	if absf(float(lg.get("shift", 0.0))) > 0.01:
		w.append("сдвинулся")
	for f: String in ["foot_l", "foot_r"]:
		var v: Array = lg.get(f, [0, 0])
		if absf(float(v[0])) > 0.01 or absf(float(v[1])) > 0.01:
			w.append("левая нога" if f == "foot_l" else "правая нога")
	if absf(float(p.get("body", {}).get("lean", 0.0))) > 0.5:
		w.append("наклон %d°" % int(p["body"]["lean"]))
	if absf(_head_tilt(p)) > 0.5:
		w.append("голова %d°" % int(_head_tilt(p)))
	for ch4: String in ["arm_r", "arm_l"]:
		if bool(p.get(ch4, {}).get("front", false)):
			w.append("%s спереди" % ("правая" if ch4 == "arm_r" else "левая"))
	if p.get("head", 0.0) is Dictionary and float(p["head"].get("drop", 0.0)) > 0.01:
		w.append("голова втянута")
	for ch2: String in ["arm_l", "arm_r"]:
		if float(p.get(ch2, {}).get("shoulder", 0.0)) > 0.01:
			w.append("левое плечо вверх" if ch2 == "arm_l" else "правое плечо вверх")
	return ", ".join(w) if not w.is_empty() else "как в покое"


func _fill_poses() -> void:
	if _pose_cards == null:
		return
	for c in _pose_cards.get_children():
		c.queue_free()
	if poses.is_empty():
		_pose_cards.add_child(_note("Здесь появятся запомненные позы — по карточке на каждую. Из них получится движение."))
		return
	var head0 := HBoxContainer.new()
	var t0 := _title("Позы: %d" % poses.size(), 21)
	t0.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head0.add_child(t0)
	var all_btn := _btn("Всё для ИИ ⧉", func() -> void: _copy_for_ai(-1), "Tile")
	all_btn.tooltip_text = "все позы по порядку, с временем и картинкой-раскадровкой: вставьте в чат с ИИ"
	head0.add_child(all_btn)
	head0.add_child(_btn("Очистить", func() -> void:
		poses.clear()
		_sel = -1
		_fill_poses()
		_save_poses(), "Tile"))
	_pose_cards.add_child(head0)
	for i in poses.size():
		var p: Dictionary = poses[i]
		var card := PanelContainer.new()
		card.theme_type_variation = "Picked" if i == _sel else ""
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", 8)
		card.add_child(v)
		# row 1: which pose, what it changes, its way in, order
		var head := HBoxContainer.new()
		head.add_theme_constant_override("separation", 8)
		var open := _btn(str(i + 1), func() -> void: _select_pose(i), "Tile")
		open.toggle_mode = true
		open.button_pressed = i == _sel
		open.custom_minimum_size = Vector2(44, 0)
		open.tooltip_text = "поставить героя в эту позу, чтобы поправить"
		head.add_child(open)
		var what := Label.new()
		what.text = _pose_words(p["pose"])
		if row == "pair":
			what.text = "слева: %s · справа: %s" % [_pose_words(p["pose"]), _pose_words(p.get("partner", {}))]
		what.clip_text = true
		what.tooltip_text = what.text
		what.mouse_filter = Control.MOUSE_FILTER_PASS
		what.custom_minimum_size = Vector2(120, 0)
		what.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		what.add_theme_font_size_override("font_size", 18)
		head.add_child(what)
		var t := _slider(0.1, 3.0, float(p["time"]), "%.2f с", func(x: float) -> void:
			poses[i]["time"] = snappedf(x, 0.05)
			_save_poses())
		t.custom_minimum_size = Vector2(170, 0)
		t.tooltip_text = "сколько секунд герой идёт в эту позу"
		head.add_child(t)
		head.add_child(_btn("↑", func() -> void: _move_pose(i, -1), "Tile"))
		head.add_child(_btn("↓", func() -> void: _move_pose(i, 1), "Tile"))
		head.add_child(_btn("✕", func() -> void: _delete_pose(i), "Tile"))
		var one := _btn("⧉", func() -> void: _copy_for_ai(i), "Tile")
		one.tooltip_text = "скопировать эту позу для ИИ: словами, числами и картинкой («вот так хочу»)"
		head.add_child(one)
		v.add_child(head)
		# row 2: how it goes there, and whether it stays
		var bottom := HBoxContainer.new()
		bottom.add_theme_constant_override("separation", 8)
		var ease_row := _seg([[EASE_NAMES[0], "inout"], [EASE_NAMES[1], "out"], [EASE_NAMES[2], "in"], [EASE_NAMES[3], "linear"]],
			str(p.get("ease", "inout")), func(e: String) -> void:
				poses[i]["ease"] = e
				_save_poses(), "Tile")
		ease_row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		bottom.add_child(ease_row)
		var hold := _toggle("Держать", bool(p.get("hold", false)), func(on: bool) -> void:
			poses[i]["hold"] = on
			_save_poses())
		hold.theme_type_variation = "Tile"
		hold.tooltip_text = "поза стоит, пока действие не отпустят (как «руки в боки»)"
		bottom.add_child(hold)

		v.add_child(bottom)
		if i == _sel:
			v.add_child(_btn("Заменить позу %d на то, как стоит герой сейчас" % (i + 1), func() -> void:
				if row == "pair":
					_pair_store()
					poses[i]["pose"] = _in_angles(_pose_for(0), _pair_actor(0))
					poses[i]["partner"] = _in_angles(_pose_for(1), _pair_actor(1))
				else:
					poses[i]["pose"] = _in_angles(pose_now)
					poses[i].erase("partner")
				_log("pose", "заменена поза %d: %s" % [i + 1, _pose_words(poses[i]["pose"])], poses[i])
				_fill_poses()
				_save_poses()
				_say("Поза %d заменена." % (i + 1)), "Main"))
		_pose_cards.add_child(card)


## The clock, under the hero on the stage's floor: pause, a frame, the speed, round and round, trail, breathing.
func _build_clock() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 21
	add_child(layer)
	_below = ColorRect.new()              # (the floor goes on under the stage when the window is taller)
	_below.color = C_CONTROL
	_below.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(_below)
	_fit_panel()
	var bar := PanelContainer.new()
	bar.theme = _theme()
	bar.add_theme_stylebox_override("panel", _box(Color(C_PAPER, 0.96), 14, 14, 12))
	bar.position = Vector2(20, SIZE.y - 150)
	bar.size = Vector2(SIZE.x - 40, 0)
	layer.add_child(bar)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	bar.add_child(v)
	var r1 := HBoxContainer.new()
	r1.add_theme_constant_override("separation", 6)
	_pause_btn = _btn("❚❚  Пауза", func() -> void: _set_paused(not paused))
	_pause_btn.custom_minimum_size = Vector2(150, 0)
	r1.add_child(_pause_btn)
	r1.add_child(_btn("Кадр ▸", func() -> void:
		_set_paused(true)
		_steps_wanted += 1))
	var sp := _seg([["0.25×", 0.25], ["0.5×", 0.5], ["1×", 1.0]], speed, func(x: float) -> void: speed = x)
	sp.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	r1.add_child(sp)
	v.add_child(r1)
	var r2 := HBoxContainer.new()
	r2.add_theme_constant_override("separation", 6)
	for t: Array in [["По кругу", _loop, func(on: bool) -> void: _loop = on],
			["След кистей и стоп", _trails, func(on: bool) -> void:
				_trails = on
				_trail.clear()],
			["Дыхание", not still, func(on: bool) -> void:
				still = not on
				_set_life()]]:
		var b := _toggle(t[0], t[1], t[2])
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		r2.add_child(b)
	v.add_child(r2)


func _say(text: String) -> void:
	if _status != null:
		_status.text = text


func _reload() -> void:
	_save_poses()
	get_tree().reload_current_scene()


# ----------------------------------------------------------------------------- mechanics

func _play(id: String) -> void:
	if not actions().has(id):
		return
	var act: Dictionary = actions()[id]
	# an action for two with one hero on the stage: the rubric's heroes come out together, and it plays again
	var for_two: bool = act.has("pair") or act.get("partner_only", false) or id in ["give", "receive"]
	if for_two and actors.size() < 2 and (cfg.get("heroes", []) as Array).size() >= 2:
		chosen = id
		row = "all"
		_reload()
		return
	chosen = id
	_mark_tile(id)
	_dirty_state = true
	_idle = 0
	_trail.clear()
	_clear_props()
	var lines: Array = []
	var paired: bool = actors.size() >= 2 and (act.has("pair") or act.get("partner_only", false) or id in ["give", "receive"])
	if paired:                                   # for two: the main hero with the one beside it (both play)
		var me: String = _main().id
		var other: String = actors.keys().filter(func(x: String) -> bool: return x != me)[0]
		if act.get("partner_only", false):       # the answering half (pushed, hugged): the other one starts it
			var lead := ""
			for k2: String in actions():
				if str(actions()[k2].get("pair", {}).get("partner", "")) == id:
					lead = k2
			if lead != "":
				lines.append({"who": other, "do": lead, "with": me, "energy": _energy, "speed": _speed, "duration": 2.5})
		elif id == "give" or id == "receive":     # hand to hand: a mug goes over (receive: the other one gives it)
			var giver: String = me if id == "give" else other
			var pid := "item_mug_" + giver
			items.add(pid, "mug", actors[giver].puppet.body_position(), {"ground_z": actors[giver].z})
			items.watch(actors[giver].motion)
			items.watch(actors[me if giver == other else other].motion)
			items.hold_now(actors[giver].motion, "hand_r", pid)
			_props.append(pid)
			lines.append({"who": giver, "give": other if giver == me else me})
		else:
			lines.append({"who": me, "do": id, "with": other, "energy": _energy, "speed": _speed, "duration": 2.5})
	for aid: String in actors:
		if paired:
			break
		var line := {"who": aid, "energy": _energy, "speed": _speed}
		if act.get("params", {}).has("side"):
			line["side"] = _side
		if act.get("group", "") == "move" and _walks(act):
			var a: Actor = actors[aid]
			line["go"] = clampf(a.puppet.body_position().x / SIZE.x + (0.25 if a.puppet.body_position().x < SIZE.x * 0.5 else -0.25), 0.1, 0.9)
			line["style"] = id
		else:
			line["do"] = _with_elbow(id)
			line["duration"] = 2.5
		if act.has("test_items"):
			line = _with_props(act, id, actors[aid], line)
		lines.append(line)
	var own_lines: bool = paired or act.has("test_items")   # (each hero its own things, its own line)
	if _over_mode:
		for line: Dictionary in lines:
			_command(line)
	elif own_lines:
		_let_go()
		_pending = {}
		_due_lines.clear()
		for line: Dictionary in lines:
			_due_lines.append(line)
	else:
		_let_go()
		_pending = {"who": "all"}
		for k: String in lines[0]:
			if k != "who":
				_pending[k] = lines[0][k]
		if lines.size() > 1 and lines[0].has("go"):
			for line: Dictionary in lines:          # (a walk: each hero across its own part of the stage)
				_due_lines.append(line)
			_pending = {}
	_say("%s%s" % [_title_of(act, id), "  · действие рубрики" if world_action_ids.has(id) else ""])
	var how := {"id": id}
	if act.get("params", {}).has("side"):
		how["side"] = _side
	if _elbow_say != "":
		how["elbow"] = _elbow_say
	if absf(_energy - 1.0) > 0.01:
		how["energy"] = _energy
	if absf(_speed - 1.0) > 0.01:
		how["speed"] = _speed
	if _over_mode:
		how["over"] = true
	_log("action", "«%s» на %s" % [_title_of(act, id), "всех героях" if actors.size() > 1 else str(_hero_def(hero_id).get("title", hero_id))], how)
	_show_faults(id)
	_update_how()


## The card's buttons change the action that plays: a pick plays it again at once, the new way.
## A new action from the list: the elbow goes back to «Сам» (a forced elbow fits one action, it wrecks the next).
func _pick_action(id: String) -> void:
	if id != chosen and _elbow_say != "":
		_elbow_say = ""
		if _elbow_seg != null:
			(_elbow_seg.get_child(0) as Button).button_pressed = true
	_play(id)


func _pick_side(v: String) -> void:
	_side = v
	_dirty_state = true
	_replay()


func _pick_elbow(v: String) -> void:
	_elbow_say = v
	_dirty_state = true
	_replay()


func _replay() -> void:
	if chosen != "" and actions().has(chosen):
		_play(chosen)


static func _has_arms(act: Dictionary) -> bool:
	for ph: Dictionary in act.get("phases", []):
		for k: String in ["arm_l", "arm_r", "arms"]:
			if ph.get(k, null) is Dictionary:
				return true
	return false


## The card says which action its buttons change, and shows only the buttons that change it.
func _update_how() -> void:
	if _how_title == null:
		return
	var some := chosen != "" and actions().has(chosen)
	_how_card.visible = some
	_how_hint.visible = not some
	if not some:
		return
	var act: Dictionary = actions()[chosen]
	var sided: bool = act.get("params", {}).has("side")
	var elbowed: bool = _has_arms(act) and not (act.get("group", "") == "move" and _walks(act))
	_side_row.visible = sided
	_elbow_row.visible = elbowed
	_how_title.text = "Как сыграть «%s»" % _title_of(act, chosen)
	_how_note.text = "Нажатие сразу переигрывает. Рука — справа или слева на экране." if sided else "Нажатие сразу переигрывает."


## THINGS for an action that needs one (its "test_items": what the engine's own check gives it): on the floor
## where the hero reaches (take, lift), in the hand (drink, put, throw, slash, the wheel), worn (an instrument:
## then it is simply the stage's "play"). Taken away again when another action is chosen.
var _props: Array = []


func _clear_props() -> void:
	for pid: String in _props:
		if items != null and items.items.has(pid):
			items.remove(pid)
	_props.clear()


func _with_props(act: Dictionary, id: String, a: Actor, line: Dictionary) -> Dictionary:
	var defs: Array = act.get("test_items", [])
	if id.begins_with("play_") and not defs.is_empty():          # an instrument: the stage hands it over and plays it
		var l := {"who": a.id, "play": str(defs[0]["card"]), "for": 3.0, "energy": _energy, "speed": _speed}
		return l
	var main_id := ""
	for d: Dictionary in defs:
		var pid := "%s_%s_%s" % [str(d["id"]), str(d["card"]), a.id]
		var x: float = a.puppet.body_position().x
		if d.has("at"):
			var at: Array = d["at"]
			var out: float = a.motion.floor_reach_x("arm_r") if at[0] is String and at[0] == "reach" else float(at[0]) * a.motion.arm
			x += out * a.motion._sign("arm_r")
		items.add(pid, str(d["card"]), Vector2(x, floor_y - 20.0), {"ground_z": a.z}.merged(d.get("def", {})))
		items.watch(a.motion)
		_props.append(pid)
		if d.has("held"):
			var hand: String = str(d["held"])
			if hand == "wear":
				items.wear_now(a.motion, pid)
			else:
				items.hold_now(a.motion, "both" if hand == "both" else "hand_" + hand.left(1), pid)
		if str(d["id"]) == "item":
			main_id = pid
	var l2 := line.duplicate()
	match id:
		"take", "lift":
			l2.erase("do")
			l2["take"] = main_id
		"put":
			l2.erase("do")
			l2["put"] = true
		"throw":
			l2.erase("do")
			l2["throw"] = true
		_:
			l2["item"] = main_id
	return l2


## The clean switch: every hero lets everything go and goes back to rest (motion.gd play_clean); the line waits.
func _let_go() -> void:
	for a: Actor in actors.values():
		_command({"who": a.id, "play": "off"})
		a.playing.clear()
		a.going = {}
		a.motion.play_clean({"id": "_rested", "phases": [{"time": 0.02}]})


func _rest(say := true) -> void:
	_pending = {}
	_due_lines.clear()
	_let_go()
	chosen = ""
	_mark_tile("")
	_update_how()
	if _faults != null:
		_faults.visible = false
	if say:
		_say("В покое.")


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


## What plays now on the main hero, each a tile that lets it go.
func _refresh_playing() -> void:
	if not _due_lines.is_empty() and _pending.is_empty():
		var calm := true
		for a: Actor in actors.values():
			calm = calm and not a.motion.busy()
		if calm:
			for line: Dictionary in _due_lines:
				_command(line)
			_due_lines.clear()
	if _playing_box == null:
		return
	var a := _main()
	var ids: Array = []
	if a != null:
		for r in a.motion.runs:
			if not r.done and not str(r.id).begins_with("_") and r.id != "rest":
				ids.append(r)
	var sig := ",".join(ids.map(func(r) -> String: return str(r.id)))
	if _playing_box.get_meta("sig", "-") == sig:
		return
	_playing_box.set_meta("sig", sig)
	for c in _playing_box.get_children():
		c.queue_free()
	if ids.is_empty():
		var none := Label.new()
		none.text = "ничего"
		none.add_theme_color_override("font_color", C_SOFT)
		_playing_box.add_child(none)
	for r in ids:
		var title: String = _title_of(actions().get(r.id, {}), str(r.id)) if actions().has(r.id) else str(r.id)
		var b := _btn(title + "   ✕", func() -> void:
			for h: Actor in actors.values():
				for rr in h.motion.runs:
					if rr.id == r.id:
						h.motion.release(rr), "Tile")
		b.tooltip_text = "отпустить"
		_playing_box.add_child(b)


## The faults the hero check found in this action on the main hero (heroes/<slug>/puppet/actions.json), in words.
func _show_faults(id: String) -> void:
	if _faults == null:
		return
	_faults.visible = false
	var h := _hero_def(hero_id)
	var f: String = str(h.get("checks", ""))
	if f == "" or not FileAccess.file_exists(f):
		return
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(f))
	if not (data is Dictionary) or not data.get("actions", {}).has(id):
		return
	var said := {}
	for r: Dictionary in data["actions"][id].get("runs", []):
		for k: String in r.get("faults", {}):
			said[FAULT_WORDS.get(k, k)] = true
	if said.is_empty():
		return
	var main: bool = data["actions"][id].get("stage1", false)
	_log("fault", "«%s» у героя «%s»: %s" % [_title_of(actions().get(id, {}), id), str(_hero_def(hero_id).get("title", hero_id)), ", ".join(said.keys())])
	_faults_text.text = "Брак у этого героя: %s. %s" % [", ".join(said.keys()),
		"Основное действие: из-за него герой не проходит проверку." if main else "Не основное: героя не валит."]
	_faults_text.add_theme_color_override("font_color", C_INK)
	_faults.visible = true


# ----------------------------------------------------------------------------- poses

## The rest pose of the main hero, in the action format (numbers only, nothing "rest").
func rest_pose(who: Actor = null) -> Dictionary:
	var a := who if who != null else _edited()
	var p := {"legs": {"drop": 0.0, "shift": 0.0, "foot_l": [0.0, 0.0], "foot_r": [0.0, 0.0]}, "body": {"lean": 0.0}, "head": 0.0}
	# (the shoulders and the head's drop are said in a pose only when moved: a pose without them is at rest there)
	for ch: String in ["arm_l", "arm_r"]:
		var at := Vector2(0.1, 0.95)
		if a != null and a.motion.rest.has(ch):
			at = MotionScript._cart(a.motion.rest[ch]["at"])
		p[ch] = {"at": [snappedf(at.x, 0.01), snappedf(at.y, 0.01)]}
	return p


## The pose on the heroes: held as a little action that owns every channel.
func _apply_pose() -> void:
	_pending = {}
	_due_lines.clear()
	_pair_store()
	for a: Actor in actors.values():
		var mine: Dictionary = pose_now
		if row == "pair":                        # (a pair: each its own pose)
			mine = _pose_for(0 if a.id == hero_id else 1)
		var ph := _full(mine)
		ph["time"] = 0.12
		var hold := _full(mine)
		hold["time"] = 1.0
		hold["loop"] = true
		a.playing.clear()
		a.going = {}
		for r in a.motion.runs:
			if r.id != "_pose":
				r.done = true
				r.owned.clear()
		a.motion.runs = a.motion.runs.filter(func(r) -> bool: return not r.done)
		a.motion.play({"id": "_pose", "phases": [ph, hold]})
	_dirty_state = true


## The pose with its arms said in ANGLES, read from the hero as it stands now (what the person sees is what is
## kept: the elbow's side is in the numbers, so the pose is the same on a tall hero and a short one).
func _in_angles(pose: Dictionary, who: Actor = null) -> Dictionary:
	var out := pose.duplicate(true)
	var a := who if who != null else _edited()
	if a == null:
		return out
	for ch: String in ["arm_l", "arm_r"]:
		if not (out.get(ch, null) is Dictionary) or out[ch].has("raise"):
			continue
		var c: Variant = a.puppet.chains["hand_" + ch.right(1)]
		var s: float = a.motion._sign(ch)
		var up: float = (a.puppet.joint_position(c.b.name) - a.puppet.joint_position(c.a.name)).angle()
		var fo: float = (a.puppet.joint_position(c.end.name) - a.puppet.joint_position(c.b.name)).angle()
		out[ch]["raise"] = snappedf(rad_to_deg(wrapf((PI / 2.0 - up) * s, -PI, PI)), 1.0)
		out[ch]["elbow"] = snappedf(rad_to_deg(wrapf((up - fo) * s, -PI, PI)), 1.0)
		out[ch].erase("at")
	return out


## Before a hand is moved by hand again, its arm goes back from angles to a place (the dots pull places).
func _arm_to_place(a: Actor, ch: String) -> void:
	if not (pose_now.get(ch, null) is Dictionary) or not pose_now[ch].has("raise"):
		return
	var mo: MotionScript = a.motion
	var d: Vector2 = (a.puppet.handle_position("hand_" + ch.right(1)) - mo._shoulder_at(ch, a.puppet.body_position())) / mo.arm
	pose_now[ch]["at"] = [snappedf(d.x * mo._sign(ch), 0.01), snappedf(d.y, 0.01)]
	pose_now[ch].erase("raise")
	pose_now[ch].erase("elbow")


## Where an arm's hand is, by its pose (a place, or angles with an even upper arm and forearm: for the way's length).
static func _hand_of(arm: Dictionary) -> Vector2:
	if arm.has("raise"):
		var r: float = deg_to_rad(float(arm["raise"]))
		var e: float = deg_to_rad(float(arm.get("elbow", 0.0)))
		return Vector2(0.5 * sin(r) + 0.5 * sin(r + e), 0.5 * cos(r) + 0.5 * cos(r + e))
	var p: Array = arm.get("at", [0, 0])
	return Vector2(p[0], p[1])


## THE LOG: what happened in the window, newest last (it outlives a reload, and is written to log.jsonl beside
## the poses for the assistant to read). Any line, or all of them, can be copied for the assistant.
static var _log_lines: Array = []    # [{t, kind, text, data}]
static var _log_open := false
static var _logged_where := ""
var _log_card: PanelContainer
var _log_list: VBoxContainer
const LOG_KEEP := 300
const LOG_KINDS := {"open": "окно", "hero": "герой", "action": "действие", "fault": "брак", "pose": "поза",
	"save": "сохранено", "ai": "ИИ", "file": "файл", "copy": "копия"}


func _log(kind: String, text: String, data: Variant = null) -> void:
	var e := {"t": Time.get_time_string_from_system(), "kind": kind, "text": text}
	if data != null:
		e["data"] = data
	_log_lines.append(e)
	if _log_lines.size() > LOG_KEEP:
		_log_lines = _log_lines.slice(_log_lines.size() - LOG_KEEP)
	var dir: String = str(cfg.get("state_dir", ""))
	if dir != "":
		DirAccess.make_dir_recursive_absolute(dir)
		var path := dir.path_join("log.jsonl")
		var f := FileAccess.open(path, FileAccess.READ_WRITE) if FileAccess.file_exists(path) else FileAccess.open(path, FileAccess.WRITE)
		if f != null:
			f.seek_end()
			f.store_line(JSON.stringify({"time": Time.get_datetime_string_from_system(false, true), "kind": kind,
				"text": text, "data": data, "world": cfg.get("world_title", ""), "hero": hero_id}))
			f.close()
	if _log_open and _log_list != null:
		_fill_log()


func _log_panel() -> Control:
	_log_card = PanelContainer.new()
	_log_card.visible = _log_open
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 6)
	_log_card.add_child(v)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	var t := _title("Журнал", 21)
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(t)
	var all := _btn("Весь журнал для ИИ ⧉", func() -> void: _copy_log(-1), "Tile")
	head.add_child(all)
	head.add_child(_btn("Очистить", func() -> void:
		_log_lines.clear()
		_fill_log(), "Tile"))
	v.add_child(head)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(0, 170)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_log_list = VBoxContainer.new()
	_log_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_log_list.add_theme_constant_override("separation", 2)
	scroll.add_child(_log_list)
	v.add_child(scroll)
	_fill_log()
	_log_list.resized.connect(func() -> void: scroll.scroll_vertical = int(_log_list.size.y))
	return _log_card


func _fill_log() -> void:
	if _log_list == null:
		return
	for c in _log_list.get_children():
		c.queue_free()
	if _log_lines.is_empty():
		_log_list.add_child(_note("Пока пусто. Сыграйте действие или запомните позу — здесь появится строка.", 16))
		return
	var from: int = maxi(_log_lines.size() - 60, 0)
	for i in range(from, _log_lines.size()):
		var e: Dictionary = _log_lines[i]
		var r := HBoxContainer.new()
		r.add_theme_constant_override("separation", 8)
		var l := Label.new()
		l.text = "%s  %s · %s" % [e["t"], LOG_KINDS.get(e["kind"], e["kind"]), e["text"]]
		l.clip_text = true
		l.tooltip_text = l.text
		l.mouse_filter = Control.MOUSE_FILTER_PASS
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		l.add_theme_font_size_override("font_size", 16)
		if e["kind"] == "fault":
			l.add_theme_color_override("font_color", C_MAIN)
		r.add_child(l)
		var cp := _btn("⧉", func() -> void: _copy_log(i), "Tile")
		cp.tooltip_text = "скопировать эту строку для ИИ"
		r.add_child(cp)
		_log_list.add_child(r)


## The head of anything copied for the assistant: where, who (the hero in words, its picture), how ready it is.
func _hero_info() -> String:
	var h: Dictionary = _hero_def(hero_id)
	var dir: String = str(h.get("dir", ""))
	var out: Array = ["Мастерская ТадамШоу · рубрика «%s» · герой «%s» (%s)" % [str(cfg.get("world_title", "")), str(h.get("title", hero_id)), hero_id]]
	var hj: Variant = JSON.parse_string(FileAccess.get_file_as_string(dir.get_base_dir().path_join("hero.json"))) if dir != "" and FileAccess.file_exists(dir.get_base_dir().path_join("hero.json")) else null
	var about: Array = []
	if hj is Dictionary:
		for k: String in ["trait", "about"]:
			var v: Variant = hj.get(k, null)
			if v is Dictionary:
				v = v.get("ru", v.get("en", ""))
			if v is String and v != "":
				about.append(v)
	if h.has("height"):
		about.append("ростом %.2f высоты кадра" % float(h["height"]))
	var ready: Dictionary = h.get("ready", {})
	if not ready.is_empty():
		about.append("готовность %d%%%s" % [int(ready.get("percent", 0)), ("; с браком: " + ", ".join(ready.get("bad", []))) if not (ready.get("bad", []) as Array).is_empty() else ""])
	if not about.is_empty():
		out.append("О герое: " + "; ".join(about))
	if dir != "" and FileAccess.file_exists(dir.path_join("portrait.png")):
		out.append("Портрет героя (открой его): " + dir.path_join("portrait.png"))
	if row == "pair":
		var b: Dictionary = _hero_def(partner_id)
		out.append("На сцене %s (второй: %s)" % [_pair_words(), partner_id])
		if str(b.get("dir", "")) != "" and FileAccess.file_exists(str(b["dir"]).path_join("portrait.png")):
			out.append("Портрет второго: " + str(b["dir"]).path_join("portrait.png"))
	elif row != "one":
		out.append("На сцене: %s" % ("все герои рубрики" if row == "all" else "пробные тела"))
	return "\n".join(out)


func _copy_log(i: int) -> void:
	var lines: Array = [_hero_info()]
	var pick: Array = [_log_lines[i]] if i >= 0 else _log_lines
	lines.append("Журнал мастерской%s:" % ("" if i >= 0 else " (%d строк, старые сверху)" % pick.size()))
	for e: Dictionary in pick:
		lines.append("%s %s · %s%s" % [e["t"], LOG_KINDS.get(e["kind"], e["kind"]), e["text"],
			("  " + JSON.stringify(e["data"])) if e.has("data") else ""])
	if i < 0:
		lines.append("Журнал файлом: " + str(cfg.get("state_dir", "")).path_join("log.jsonl"))
	DisplayServer.clipboard_set("\n".join(lines))
	_say("Скопировано для ИИ: %s. Вставьте в чат." % ("строка журнала" if i >= 0 else "весь журнал"))


## COPY FOR AI: what the person shows, for the assistant to see. The hero is put in the pose (or in each pose in
## turn), a picture is taken without the dots and kept beside the poses (.tadam/workshop/shots/), and the
## clipboard gets the rubric, the hero, the pose in words and in numbers, the timing, and the picture's path.
var _copying := false


func _copy_for_ai(which: int) -> void:
	if _copying or poses.is_empty():
		return
	_copying = true
	_pair_store()
	var keep := pose_now.duplicate(true)
	var keep_pair: Array = pair_pose.duplicate(true)
	var keep_sel := _sel
	var dir: String = str(cfg.get("state_dir", "")).path_join("shots")
	DirAccess.make_dir_recursive_absolute(dir)
	var idx: Array = [which] if which >= 0 else range(poses.size())
	_say("Снимаю %s…" % ("позу %d" % (which + 1) if which >= 0 else "позы"))
	var pics: Array = []
	for i: int in idx:
		var same: bool = tab == 1 and JSON.stringify(poses[i]["pose"]) == JSON.stringify(_in_angles(_pose_for(0), _pair_actor(0)) if row == "pair" else _in_angles(pose_now))
		if row == "pair" and same:
			same = JSON.stringify(poses[i].get("partner", {})) == JSON.stringify(_in_angles(_pose_for(1), _pair_actor(1)))
		if not same:                       # (the pose already on the hero is taken as it stands: nothing moves)
			_put_pose(i)
			_apply_pose()
		pics.append(await _snap_hero())
	var files: Array = []
	for k in pics.size():
		var f: String = dir.path_join("pose-%d.png" % (int(idx[k]) + 1))
		(pics[k] as Image).save_png(f)
		files.append(f)
	var sheet := ""
	if which < 0 and pics.size() > 1:
		sheet = dir.path_join("poses.png")
		_strip(pics).save_png(sheet)
	pair_pose = keep_pair
	pose_now = keep
	if row == "pair":
		pair_pose[pair_edit] = pose_now
	_sel = keep_sel
	_apply_pose()
	var lines: Array = [_hero_info()]
	var units := "руки — углы в градусах: raise 0 вниз, 90 в сторону, 180 вверх; elbow + сгиб в ту же сторону; ноги и тело — в длинах ноги"
	if row == "pair":
		var a0 := _pair_actor(0)
		var b0 := _pair_actor(1)
		var gap0: float = (absf(b0.motion._rest_body.x - a0.motion._rest_body.x) - _half_width(a0) - _half_width(b0)) / maxf(0.5 * (a0.arm + b0.arm), 1.0)
		lines.append("Поза для двоих: обе позы записаны как стоят (у каждого arm_r — рука справа на экране); при сохранении правый пишется зеркально в <id>_b. Расстояние: pair.gap %.2f" % gap0)
	if which >= 0 and row == "pair":
		var pp: Dictionary = poses[which]
		lines.append("Поза %d из %d — вот так я хочу. Слева: %s. Справа: %s" % [which + 1, poses.size(), _pose_words(pp["pose"]), _pose_words(pp.get("partner", {}))])
		lines.append("Картинка (открой её): %s" % files[0])
		lines.append("Слева числами (%s): %s" % [units, JSON.stringify(pp["pose"])])
		lines.append("Справа числами: %s" % JSON.stringify(pp.get("partner", {})))
	elif which >= 0:
		var p: Dictionary = poses[which]
		lines.append("Поза %d из %d — вот так я хочу: %s" % [which + 1, poses.size(), _pose_words(p["pose"])])
		lines.append("Картинка (открой её): %s" % files[0])
		lines.append("Поза числами (%s): %s" % [units, JSON.stringify(p["pose"])])
	else:
		lines.append("Движение из %d поз — вот так я хочу:" % poses.size())
		if sheet != "":
			lines.append("Раскадровка, слева направо (открой её): %s" % sheet)
		for k in poses.size():
			var p2: Dictionary = poses[k]
			lines.append("%d. %.2f с, %s%s — %s" % [k + 1, float(p2["time"]), EASE_WORDS.get(str(p2.get("ease", "inout")), "плавно"),
				", держать" if bool(p2.get("hold", false)) else "", _pose_words(p2["pose"])])
			lines.append("   картинка: %s" % files[k])
			if row == "pair":
				lines.append("   справа: %s" % _pose_words(p2.get("partner", {})))
				lines.append("   слева числами: %s" % JSON.stringify(p2["pose"]))
				lines.append("   справа числами: %s" % JSON.stringify(p2.get("partner", {})))
			else:
				lines.append("   числами: %s" % JSON.stringify(p2["pose"]))
		lines.append("Все позы файлом: %s · черновик действия: tadam action from-poses <id> --title \"…\"" % str(cfg.get("state_dir", "")).path_join("poses.json"))
	DisplayServer.clipboard_set("\n".join(lines))
	_log("copy", "скопировано для ИИ: %s" % ("поза %d" % (which + 1) if which >= 0 else "все позы (%d)" % poses.size()))
	_copying = false
	_say("Скопировано для ИИ: %s. Вставьте в чат." % ("поза %d с картинкой" % (which + 1) if which >= 0 else "все позы с раскадровкой"))


const EASE_WORDS := {"inout": "плавно", "out": "резкий старт", "in": "резкий конец", "linear": "ровно"}


## The hero as it stands now, still (the dots hidden, the idle life paused while the picture is taken).
func _snap_hero() -> Image:
	var was_still := still
	still = true
	_set_life()
	_dots.visible = false
	for k in 45:
		await get_tree().physics_frame
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	_dots.visible = true
	still = was_still
	_set_life()
	# the hero's box on the stage (its dots, and a margin), in the picture's pixels
	var lo := Vector2(INF, INF)
	var hi := Vector2(-INF, -INF)
	for a: Actor in ([_pair_actor(0), _pair_actor(1)] if row == "pair" else [_main()]):
		if a == null:
			continue
		var pts := _dot_points(a)
		for k: String in pts:
			lo = lo.min(pts[k])
			hi = hi.max(pts[k])
	var vis: Vector2 = get_viewport().get_visible_rect().size
	var kx: float = float(img.get_width()) / vis.x
	var ky: float = float(img.get_height()) / vis.y
	var top: float = lo.y - (hi.y - lo.y) * 0.25
	var r := Rect2i(int(maxf(lo.x - 160.0, 0.0) * kx), int(maxf(top, 0.0) * ky),
		int((minf(hi.x + 160.0, SIZE.x) - maxf(lo.x - 160.0, 0.0)) * kx), int((minf(floor_y + 30.0, SIZE.y) - maxf(top, 0.0)) * ky))
	r = r.intersection(Rect2i(0, 0, img.get_width(), img.get_height()))
	return img.get_region(r)


## The pictures side by side, one height, on the stage's paper.
static func _strip(pics: Array) -> Image:
	var h := 0
	for im: Image in pics:
		h = maxi(h, im.get_height())
	var w := 0
	var scaled: Array = []
	for im: Image in pics:
		var c: Image = im.duplicate()
		c.resize(int(c.get_width() * float(h) / c.get_height()), h, Image.INTERPOLATE_BILINEAR)
		scaled.append(c)
		w += c.get_width() + 16
	var out := Image.create(w, h, false, (scaled[0] as Image).get_format())
	out.fill(Color("efe8da"))
	var x := 0
	for c: Image in scaled:
		out.blit_rect(c, Rect2i(0, 0, c.get_width(), c.get_height()), Vector2i(x, 0))
		x += c.get_width() + 16
	return out


func _show_front() -> void:
	if _front_seg == null:
		return
	var fr := "r" if bool(pose_now.get("arm_r", {}).get("front", false)) else ("l" if bool(pose_now.get("arm_l", {}).get("front", false)) else "")
	for b: Button in _front_seg.get_children():
		b.set_pressed_no_signal(["", "r", "l"][b.get_index()] == fr)


## A pose as it plays: what it does not say (a shoulder, the head's drop) is at rest, not left where it was.
static func _full(pose: Dictionary) -> Dictionary:
	var out := pose.duplicate(true)
	for ch: String in ["arm_l", "arm_r"]:
		if out.get(ch, null) is Dictionary and not out[ch].has("shoulder"):
			out[ch]["shoulder"] = 0.0
		if out.get(ch, null) is Dictionary and not out[ch].has("front"):
			out[ch]["front"] = false
	var h: Variant = out.get("head", 0.0)
	out["head"] = h if h is Dictionary else {"tilt": float(h), "drop": 0.0}
	return out


static func _head_tilt(pose: Dictionary) -> float:
	var h: Variant = pose.get("head", 0.0)
	return float(h.get("tilt", 0.0)) if h is Dictionary else float(h)


func _fix() -> void:
	if row == "pair":                            # a pair: both poses at once, the way as long as the longer one
		_pair_store()
		var ka := _in_angles(_pose_for(0), _pair_actor(0))
		var kb := _in_angles(_pose_for(1), _pair_actor(1))
		var ba: Dictionary = poses[-1]["pose"] if not poses.is_empty() else rest_pose(_pair_actor(0))
		var bb: Dictionary = poses[-1].get("partner", rest_pose(_pair_actor(1))) if not poses.is_empty() else rest_pose(_pair_actor(1))
		var e := {"pose": ka, "partner": kb, "time": maxf(way_time(ba, ka), way_time(bb, kb)), "ease": "inout", "hold": false}
		poses.append(e)
		_log("pose", "запомнена поза %d (%s): слева %s; справа %s" % [poses.size(), _pair_words(), _pose_words(ka), _pose_words(kb)], e)
		_sel = -1
		_fill_poses()
		_save_poses()
		_say("Поза %d запомнена для обоих. Поставьте следующую или нажмите «Показать движение»." % poses.size())
		return
	var before: Dictionary = poses[-1]["pose"] if not poses.is_empty() else rest_pose()
	var kept := _in_angles(pose_now)
	poses.append({"pose": kept, "time": way_time(before, kept), "ease": "inout", "hold": false})
	_log("pose", "запомнена поза %d: %s" % [poses.size(), _pose_words(kept)], kept)
	_sel = -1
	_fill_poses()
	_save_poses()
	_say("Поза %d запомнена. Поставьте следующую или нажмите «Показать движение»." % poses.size())


## How long a hand (or a foot, or the body) needs from one pose to the next: the longest way at HAND_PACE.
static func way_time(a: Dictionary, b: Dictionary) -> float:
	var far := 0.0
	for ch: String in ["arm_l", "arm_r"]:
		if a.get(ch, null) is Dictionary and b.get(ch, null) is Dictionary:
			far = maxf(far, _hand_of(a[ch]).distance_to(_hand_of(b[ch])))
	if a.get("legs", null) is Dictionary and b.get("legs", null) is Dictionary:
		far = maxf(far, 1.5 * absf(float(a["legs"].get("drop", 0.0)) - float(b["legs"].get("drop", 0.0))))
		for f: String in ["foot_l", "foot_r"]:
			var p: Array = a["legs"].get(f, [0, 0])
			var q: Array = b["legs"].get(f, [0, 0])
			far = maxf(far, 1.5 * Vector2(p[0], p[1]).distance_to(Vector2(q[0], q[1])))
	if a.get("body", null) is Dictionary and b.get("body", null) is Dictionary:
		far = maxf(far, absf(float(a["body"].get("lean", 0.0)) - float(b["body"].get("lean", 0.0))) / 40.0)
	far = maxf(far, absf(_head_tilt(a) - _head_tilt(b)) / 50.0)
	for ch3: String in ["arm_l", "arm_r"]:
		far = maxf(far, absf(float(a.get(ch3, {}).get("shoulder", 0.0)) - float(b.get(ch3, {}).get("shoulder", 0.0))) * 3.0)
	return snappedf(clampf(far / HAND_PACE + 0.15, 0.25, 2.0), 0.05)


func _select_pose(i: int) -> void:
	if i < 0 or i >= poses.size():
		return
	_sel = i
	_put_pose(i)
	_show_front()
	_fill_poses()
	_apply_pose()
	_say("Герой в позе %d. Поправьте точки и нажмите красную кнопку на её карточке." % (i + 1))


## The i-th pose onto the hero (a pair: each its own half of it).
func _put_pose(i: int) -> void:
	if row == "pair":
		pair_pose[0] = (poses[i]["pose"] as Dictionary).duplicate(true)
		pair_pose[1] = (poses[i].get("partner", rest_pose(_pair_actor(1))) as Dictionary).duplicate(true)
		pose_now = pair_pose[pair_edit]
	else:
		pose_now = (poses[i]["pose"] as Dictionary).duplicate(true)


## A pair: the list of poses of one of them (0 the left one, 1 the right one), timing and all.
func _half_list(k: int) -> Array:
	var out: Array = []
	for p: Dictionary in poses:
		var e: Dictionary = p.duplicate(true)
		e.erase("partner")
		if k == 1:
			e["pose"] = (p.get("partner", rest_pose(_pair_actor(1))) as Dictionary).duplicate(true)
		out.append(e)
	return out


## A pose for the other side: what an action played mirrored ("side": "left") turns back into this pose.
## Arms and feet are said outward from their own side, so only the sides swap; a lean and a tilt turn round.
static func mirror_pose(p: Dictionary) -> Dictionary:
	var out := p.duplicate(true)
	out.erase("arm_l")
	out.erase("arm_r")
	if p.has("arm_r"):
		out["arm_l"] = (p["arm_r"] as Dictionary).duplicate(true) if p["arm_r"] is Dictionary else p["arm_r"]
	if p.has("arm_l"):
		out["arm_r"] = (p["arm_l"] as Dictionary).duplicate(true) if p["arm_l"] is Dictionary else p["arm_l"]
	if p.get("legs", null) is Dictionary:
		var lg: Dictionary = (p["legs"] as Dictionary).duplicate(true)
		for key: String in ["foot", "hip", "knee"]:
			var l: Variant = lg.get(key + "_l", null)
			var r: Variant = lg.get(key + "_r", null)
			lg.erase(key + "_l")
			lg.erase(key + "_r")
			if r != null:
				lg[key + "_l"] = r
			if l != null:
				lg[key + "_r"] = l
		if lg.has("shift"):
			lg["shift"] = -float(lg["shift"])
		out["legs"] = lg
	if p.get("body", null) is Dictionary:
		for k: String in ["lean", "chest"]:
			if (p["body"] as Dictionary).has(k):
				out["body"][k] = -float(p["body"][k])
	var h: Variant = p.get("head", null)
	if h is float or h is int:
		out["head"] = -float(h)
	elif h is Dictionary and (h as Dictionary).has("tilt"):
		out["head"]["tilt"] = -float(h["tilt"])
	return out


func _move_pose(i: int, d: int) -> void:
	if i + d < 0 or i + d >= poses.size():
		return
	var p: Variant = poses[i]
	poses.remove_at(i)
	poses.insert(i + d, p)
	_sel = i + d if _sel == i else _sel
	_fill_poses()
	_save_poses()


func _delete_pose(i: int) -> void:
	_log("pose", "удалена поза %d" % (i + 1))
	poses.remove_at(i)
	_sel = -1 if _sel == i else (_sel - 1 if _sel > i else _sel)
	_fill_poses()
	_save_poses()


## The pose list as an action (the same as `tadam action from-poses`): a phase a pose, only what changed from the
## pose before, then back to rest.
static func poses_action(list: Array, id: String, title: String, base: Dictionary) -> Dictionary:
	var phases: Array = []
	var prev: Dictionary = base
	var used := {}
	for p: Dictionary in list:
		var pose: Dictionary = p["pose"]
		var ph := {"time": float(p.get("time", 0.5))}
		if str(p.get("ease", "inout")) != "inout":
			ph["ease"] = str(p["ease"])
		if p.get("hold", false):
			ph["loop"] = true
		for ch: String in ["legs", "body", "head", "arm_l", "arm_r"]:
			if pose.has(ch) and JSON.stringify(pose[ch]) != JSON.stringify(prev.get(ch, null)):
				ph[ch] = pose[ch]
				used[ch] = true
		phases.append(ph)
		prev = pose
	var back := {"name": "return", "time": 0.45}
	for ch: String in used:
		back[ch] = "rest"
	phases.append(back)
	return {"id": id, "title": title, "group": "gesture", "params": {"side": "right"}, "phases": phases}


func _play_poses() -> void:
	if poses.is_empty():
		_say("Сначала запомните хотя бы одну позу.")
		return
	var act := poses_action(poses, "_poses", "позы", rest_pose())
	actions()["_poses"] = act
	if row == "pair":                            # each its own half (both as they stand: no mirroring here)
		_pair_store()
		for k in 2:
			var half := poses_action(_half_list(k), "_poses", "позы", rest_pose(_pair_actor(k)))
			if _pair_actor(k) != null:
				_pair_actor(k).motion.play_clean(half, {"side": "right", "duration": 1.5})
		_say("Движение пары из %d поз." % poses.size())
		return
	for a: Actor in actors.values():
		a.motion.play_clean(act, {"side": "right", "duration": 1.5})
	_say("Движение из %d поз. Не нравится переход — поправьте время и плавность на карточке." % poses.size())


func _save_action() -> void:
	var id := _save_id.text.strip_edges()
	if not RegEx.create_from_string("^[a-z][a-z0-9_]{0,39}$").search(id):
		_say("Имя — латинские строчные буквы, цифры и _, с буквы: salute, big_wave.")
		return
	if poses.is_empty():
		_say("Сначала запомните позы.")
		return
	var core: bool = cfg.get("core", false)
	var lib := ProjectSettings.globalize_path("res://actions")
	if not core and FileAccess.file_exists(lib.path_join(id + ".json")):
		_say("«%s» уже есть в общей библиотеке. Выберите другое имя." % id)
		return
	var dir: String = str(cfg.get("save_dir", ""))
	if dir == "":
		_say("Некуда сохранять: откройте мастерскую в папке мира.")
		return
	DirAccess.make_dir_recursive_absolute(dir)
	var path := dir.path_join(id + ".json")
	var title := _save_title.text.strip_edges()
	if row == "pair":
		_save_pair(id, title, dir, core)
		return
	var act := poses_action(poses, id, title if title != "" else id, rest_pose())
	if FileAccess.file_exists(path):
		var old: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if old is Dictionary:                    # (its passport stays: group, params, author ...)
			for k: String in old:
				if not act.has(k) or k in ["group", "params", "title"] and title == "":
					act[k] = old[k]
			act["phases"] = poses_action(poses, id, "", rest_pose())["phases"]
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(JSON.stringify(act, " ", false) + "\n")
	f.close()
	_log("save", "сохранено действие «%s» из %d поз: %s" % [id, poses.size(), path])
	reload_actions()
	_stamp = _actions_stamp()
	_fill_tiles()
	_say("Сохранено: «%s» (%s).%s" % [title if title != "" else id, id, " Общая библиотека: изменится во всех мирах после выпуска." if core else " Оно уже в списке действий."])


## A pair saved: the left one's half leads (`<id>`, with "pair": how far apart, and its partner), the right
## one's is `<id>_b` ("partner_only"). The stage plays the partner MIRRORED (its near hand is its left), so its
## half is written mirrored: played, it turns back into the poses that were set here.
func _save_pair(id: String, title: String, dir: String, core: bool) -> void:
	var a := _pair_actor(0)
	var b := _pair_actor(1)
	if a == null or b == null:
		return
	var id_b := id + "_b"
	if not core and FileAccess.file_exists(ProjectSettings.globalize_path("res://actions").path_join(id_b + ".json")):
		_say("«%s» уже есть в общей библиотеке. Выберите другое имя." % id_b)
		return
	_pair_store()
	var dx: float = absf(b.motion._rest_body.x - a.motion._rest_body.x)
	var gap: float = snappedf(clampf((dx - _half_width(a) - _half_width(b)) / maxf(0.5 * (a.arm + b.arm), 1.0), -0.5, 3.0), 0.01)
	var name: String = title if title != "" else id
	var lead := poses_action(_half_list(0), id, name, rest_pose(a))
	lead["group"] = "two"
	lead["pair"] = {"gap": gap, "view": "front", "partner": id_b}
	var half_b: Array = _half_list(1)
	for e: Dictionary in half_b:
		e["pose"] = mirror_pose(e["pose"])
	var other := poses_action(half_b, id_b, name + " (второй в паре)", mirror_pose(rest_pose(b)))
	other["group"] = "two"
	other["partner_only"] = true
	for pair: Array in [[lead, dir.path_join(id + ".json")], [other, dir.path_join(id_b + ".json")]]:
		var act: Dictionary = pair[0]
		var path: String = pair[1]
		if FileAccess.file_exists(path):
			var old: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
			if old is Dictionary:                # (its passport stays: params, author ...)
				for k: String in old:
					if not act.has(k) or (k == "title" and title == ""):
						act[k] = old[k]
		var f := FileAccess.open(path, FileAccess.WRITE)
		f.store_string(JSON.stringify(act, " ", false) + "\n")
		f.close()
	_log("save", "сохранено действие для двоих «%s» + «%s» из %d поз (%s, расстояние %.2f): %s" % [id, id_b, poses.size(), _pair_words(), gap, dir], lead["pair"])
	reload_actions()
	_stamp = _actions_stamp()
	_fill_tiles()
	_say("Сохранено для двоих: «%s» (%s и %s). В «Смотреть действия» левый начнёт, правый ответит." % [name, id, id_b])


# ----------------------------------------------------------------------------- the dots

func _dot_points(a: Actor) -> Dictionary:
	var p: Puppet = a.puppet
	var out := {"hand_l": p.handle_position("hand_l"), "hand_r": p.handle_position("hand_r"),
		"foot_l": p.handle_position("foot_l"), "foot_r": p.handle_position("foot_r"),
		"body": p.body_position()}
	# the lean: between the shoulders; the head: its crown (two dots on the face read as a face)
	if p.chains.has("hand_l") and p.chains.has("hand_r"):
		var lift: float = (float(pose_now.get("arm_l", {}).get("shoulder", 0.0)) + float(pose_now.get("arm_r", {}).get("shoulder", 0.0))) * 0.5
		out["neck"] = (p.chains["hand_l"].a.node.global_position + p.chains["hand_r"].a.node.global_position) * 0.5 				+ Vector2(0.0, lift * a.motion.arm)          # (where the shoulders are at rest: a shrug does not move it)
	if p.parts.has("head"):
		var hp = p.parts["head"]
		out["head"] = hp.node.to_global(Vector2(hp.painted.get_center().x, hp.painted.position.y + hp.painted.size.y * 0.1))
	for sd: String in ["l", "r"]:              # the shoulders: on the upper arm's joint
		if p.chains.has("hand_" + sd):
			out["shoulder_" + sd] = p.chains["hand_" + sd].a.node.global_position
	return out


func _draw_dots(canvas: Node2D) -> void:
	_draw_stands(canvas)
	var a := _edited()
	if a == null:
		return
	if _trails:
		for h: String in _trail:
			var tr: Array = _trail[h]
			for i in range(1, tr.size()):
				canvas.draw_line(tr[i - 1], tr[i], Color(C_MAIN, float(i) / tr.size() * 0.8), 3.0, true)
	if tab != 1:
		return
	var pts := _dot_points(a)
	for k: String in pts:
		var at: Vector2 = pts[k]
		var col: Color = C_DOT_BODY if k in ["body", "neck", "head", "shoulder_l", "shoulder_r"] else C_DOT_LIMB
		var big: float = DOT * (1.25 if k == _drag or k == _hover else 1.0)
		canvas.draw_circle(at, big + 3.0, Color.WHITE, true, -1.0, true)
		canvas.draw_circle(at, big, Color(col, 0.95 if k == _drag or k == _hover else 0.8), true, -1.0, true)
	var font := ThemeDB.fallback_font
	var name := _drag if _drag != "" else _hover
	if name != "":
		var at2: Vector2 = pts[name] + Vector2(22, -18)
		var text: String = DOT_NAMES.get(name, name)
		if name.begins_with("hand"):
			var arm: Dictionary = pose_now.get("arm_" + name.right(1), {})
			var extra: Array = []
			if arm.has("look"):
				extra.append(LOOK_NAMES.get(arm["look"], arm["look"]))
			if arm.has("wrist"):
				extra.append("поворот %d°" % int(arm["wrist"]))
			if arm.get("elbow", null) is String:
				extra.append(ELBOW_NAMES.get(arm["elbow"], arm["elbow"]))
			if not extra.is_empty():
				text += " · " + ", ".join(extra)
		var size := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 20)
		if at2.x + size.x + 20 > SIZE.x:
			at2.x = pts[name].x - size.x - 42
		canvas.draw_rect(Rect2(at2 + Vector2(-10, -size.y + 2), size + Vector2(20, 10)), C_INK, true)
		canvas.draw_string(font, at2, text, HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color.WHITE)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_F and tab == 1 and not (_save_id != null and (_save_id.has_focus() or _save_title.has_focus())):
			_fix()
		elif event.keycode == KEY_SPACE:
			_set_paused(not paused)
		elif event.keycode == KEY_PERIOD:
			_set_paused(true)
			_steps_wanted += 1


## The dots take the mouse BEFORE the stage's own layers (titles, effects: full-screen controls that would eat
## every click), but only over the stage and not over the clock under the hero.
func _input(event: InputEvent) -> void:
	if not (event is InputEventMouse):
		return
	if row == "pair" and (_stand_drag >= 0 or _drag == ""):
		var m0: Vector2 = get_canvas_transform().affine_inverse() * (event as InputEventMouse).position
		if (m0.x < SIZE.x or _stand_drag >= 0) and _stand_mouse(event, m0):
			get_viewport().set_input_as_handled()
			return
	if tab != 1:
		return
	var a := _edited()
	if a == null:
		return
	var m: Vector2 = get_canvas_transform().affine_inverse() * (event as InputEventMouse).position   # (the event's own spot, never the OS cursor)
	if (m.x >= SIZE.x or m.y >= SIZE.y - 160.0) and _drag == "":
		_hover = ""
		return
	if _dots_mouse(event, a, m):
		get_viewport().set_input_as_handled()


func _dots_mouse(event: InputEvent, a: Actor, m: Vector2) -> bool:
	if event is InputEventMouseMotion:
		if _drag != "":
			_drag_to(a, _drag, m + _drag_off)
			return true
		_hover = _pick(a, m)
		return false
	if event is InputEventMouseButton:
		var e := event as InputEventMouseButton
		var k := _pick(a, m)
		if e.button_index == MOUSE_BUTTON_LEFT:
			if e.pressed and k != "":
				_drag = k
				_drag_off = _dot_points(a)[k] - m
				return true
			if not e.pressed and _drag != "":
				_drag = ""
				return true
			return false
		elif e.pressed and e.button_index == MOUSE_BUTTON_RIGHT and k.begins_with("hand"):
			if e.shift_pressed:
				_arm_to_place(a, "arm_" + k.right(1))        # (the elbow is chosen for a place, not for angles)
			var arm: Dictionary = pose_now["arm_" + k.right(1)]
			if e.shift_pressed:
				var i := (ELBOWS.find(str(arm.get("elbow", ""))) + 1) % ELBOWS.size()
				if ELBOWS[i] == "":
					arm.erase("elbow")
				else:
					arm["elbow"] = ELBOWS[i]
			else:
				var j := (LOOKS.find(str(arm.get("look", "auto"))) + 1) % LOOKS.size()
				if LOOKS[j] == "auto":
					arm.erase("look")
				else:
					arm["look"] = LOOKS[j]
			_apply_pose()
			return true
		elif e.pressed and e.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN] and k.begins_with("hand"):
			var arm2: Dictionary = pose_now["arm_" + k.right(1)]
			var w := clampf(float(arm2.get("wrist", 0.0)) + (5.0 if e.button_index == MOUSE_BUTTON_WHEEL_UP else -5.0), -80.0, 80.0)
			if absf(w) < 0.5:
				arm2.erase("wrist")
			else:
				arm2["wrist"] = w
			_apply_pose()
			return true
	return false


func _pick(a: Actor, m: Vector2) -> String:
	var best := ""
	var best_d := REACH
	var pts := _dot_points(a)
	for k: String in pts:
		var d: float = (pts[k] as Vector2).distance_to(m)
		if d < best_d:
			best_d = d
			best = k
	return best


## A dot pulled to a point of the stage: the pose in the action's measures (arm and leg lengths from the
## shoulder, the hip, the foot's place; degrees), for the action's right side.
func _drag_to(a: Actor, k: String, to: Vector2) -> void:
	var mo: MotionScript = a.motion
	var p: Puppet = a.puppet
	if k.begins_with("hand"):
		var ch := "arm_" + k.right(1)
		_arm_to_place(a, ch)
		var sh: Vector2 = mo._shoulder_at(ch, p.body_position())
		var d := (to - sh) / mo.arm
		d = d.limit_length(1.0)
		pose_now[ch]["at"] = [snappedf(d.x * mo._sign(ch), 0.01), snappedf(d.y, 0.01)]
	elif k.begins_with("foot"):
		var home: Vector2 = mo.foot_home.get(k, p.handle_position(k))
		var off := (to - home) / mo.leg
		pose_now["legs"][k] = [snappedf(clampf(off.x * mo._sign(k), -0.6, 0.8), 0.01), snappedf(clampf(-off.y, 0.0, 0.9), 0.01)]
	elif k == "body":
		var off2 := (to - mo._rest_body) / mo.leg
		pose_now["legs"]["drop"] = snappedf(clampf(off2.y, 0.0, 0.6), 0.01)
		pose_now["legs"]["shift"] = snappedf(clampf(off2.x, -0.4, 0.4), 0.01)
	elif k == "neck":
		var v := to - p.body_position()
		pose_now["body"]["lean"] = snappedf(clampf(rad_to_deg(atan2(v.x, -v.y)), -45.0, 45.0), 1.0)
	elif k == "head":
		# round the neck joint: aside tilts it; pulled down toward the neck, the head is drawn into the collar
		var hp: Variant = p.parts["head"]
		var drop_now: float = float(pose_now["head"].get("drop", 0.0)) if pose_now["head"] is Dictionary else 0.0
		var hh: float = (hp.painted as Rect2).size.y * absf(p.scale.y)
		var neck: Vector2 = (hp.node.global_position as Vector2) - Vector2(0.0, drop_now * hh)    # (where it sits undrawn)
		var v2: Vector2 = to - neck
		var crown_len: float = absf(hp.painted.position.y + hp.painted.size.y * 0.1) * absf(p.scale.y)
		var tilt: float = snappedf(clampf(rad_to_deg(atan2(v2.x, -v2.y)) - float(pose_now["body"].get("lean", 0.0)), -35.0, 35.0), 1.0)
		var drop: float = snappedf(clampf((crown_len - v2.length()) / maxf(hh, 1.0), -0.15, 0.25), 0.01)
		pose_now["head"] = tilt if absf(drop) < 0.02 else {"tilt": tilt, "drop": drop}
	elif k.begins_with("shoulder"):
		var ch2 := "arm_" + k.right(1)
		var up_now: float = float(pose_now[ch2].get("shoulder", 0.0))
		var home_y: float = p.chains["hand_" + k.right(1)].a.node.global_position.y + up_now * mo.arm
		var up: float = snappedf(clampf((home_y - to.y) / mo.arm, -0.08, 0.16), 0.01)
		if absf(up) < 0.01:
			pose_now[ch2].erase("shoulder")
		else:
			pose_now[ch2]["shoulder"] = up
	_apply_pose()


# ----------------------------------------------------------------------------- the files

func _actions_stamp() -> String:
	var s := ""
	for d: String in [ProjectSettings.globalize_path("res://actions"), world_actions_dir]:
		if d == "" or not DirAccess.dir_exists_absolute(d):
			continue
		for f in DirAccess.get_files_at(d):
			if f.ends_with(".json") and not f.ends_with(".check.json"):
				s += "%s:%d;" % [f, FileAccess.get_modified_time(d.path_join(f))]
	return s


## An action file changed on disk (Claude wrote it): read the library again; the action on the stage plays again.
func _watch_files() -> void:
	var st := _actions_stamp()
	if st != _stamp:
		_stamp = st
		reload_actions()
		_fill_tiles()
		if tab == 0 and chosen != "" and actions().has(chosen):
			_play(chosen)
			_say("Файл изменился — «%s» играет заново." % _title_of(actions()[chosen], chosen))
			_log("file", "файл действия изменился, «%s» играет заново" % _title_of(actions()[chosen], chosen))
	var dir: String = str(cfg.get("state_dir", ""))
	if dir == "":
		return
	var cmd_path := dir.path_join("cmd.json")
	if FileAccess.file_exists(cmd_path):
		var c: Variant = JSON.parse_string(FileAccess.get_file_as_string(cmd_path))
		if c is Dictionary and int(c.get("n", 0)) > _cmd_seen:
			_cmd_seen = int(c["n"])
			match str(c.get("do", "")):
				"fix":
					_log("ai", "ИИ попросил запомнить позу")
					if tab == 1:
						_fix()
				"pose":
					if c.get("pose", null) is Dictionary:
						pose_now = c["pose"]
						_apply_pose()
				"play":
					if actions().has(str(c.get("action", ""))):
						_show_mode(0)
						_pick_action(str(c["action"]))
			_dirty_state = true


func _load_poses() -> void:
	var dir: String = str(cfg.get("state_dir", ""))
	if dir == "" or not FileAccess.file_exists(dir.path_join("poses.json")):
		return
	var d: Variant = JSON.parse_string(FileAccess.get_file_as_string(dir.path_join("poses.json")))
	if d is Dictionary and d.get("poses", null) is Array:
		poses = d["poses"]
	if FileAccess.file_exists(dir.path_join("cmd.json")):
		var c: Variant = JSON.parse_string(FileAccess.get_file_as_string(dir.path_join("cmd.json")))
		_cmd_seen = int(c.get("n", 0)) if c is Dictionary else 0


func _save_poses() -> void:
	var dir: String = str(cfg.get("state_dir", ""))
	if dir == "":
		return
	DirAccess.make_dir_recursive_absolute(dir)
	var f := FileAccess.open(dir.path_join("poses.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify({"hero": hero_id, "side": "right", "rest": rest_pose(), "poses": poses}, " ", false) + "\n")
	f.close()
	_dirty_state = true


## What is chosen now, for Claude: .tadam/workshop/state.json.
func _write_state() -> void:
	_dirty_state = false
	var dir: String = str(cfg.get("state_dir", ""))
	if dir == "":
		return
	DirAccess.make_dir_recursive_absolute(dir)
	var a := _main()
	var st := {"world": cfg.get("world", ""), "world_title": cfg.get("world_title", ""), "hero": hero_id, "row": row, "partner": partner_id if row == "pair" else "", "pair_edit": pair_edit, "tab": ["mechanics", "poses"][tab], "action": chosen, "side": _side, "elbow": _elbow_say,
		"view": a.view if a != null else "front", "pose": pose_now, "poses": poses.size(), "pose_selected": _sel + 1,
		"cmd_seen": _cmd_seen, "at": Time.get_datetime_string_from_system(false, true)}
	var f := FileAccess.open(dir.path_join("state.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify(st, " ", false) + "\n")
	f.close()


# ----------------------------------------------------------------------------- checks of the window itself

## WORKSHOP_SEQ="still@5,tab:1@20,drag:hand_r:560:420@40,fix@80,select:1@100,where:<file>@110,shot:<file>@120,quit@130":
## steps it by itself (tests), quits after.
static var _frames := 0
static var _seq: Array = []


func _scripted() -> void:
	if not OS.has_environment("WORKSHOP_SEQ"):
		return
	_frames += 1
	if _frames == 1:
		for part in OS.get_environment("WORKSHOP_SEQ").split(","):
			_seq.append([int(part.get_slice("@", 1)), part.get_slice("@", 0)])
	for e: Array in _seq:
		if e[0] != _frames:
			continue
		var bits: PackedStringArray = str(e[1]).split(":")
		match bits[0]:
			"tab":
				_show_mode(int(bits[1]))
			"play":
				_pick_action(bits[1])
			"row":                         # row:proof: as the «Один герой / Все герои / Пробные тела» buttons do
				row = bits[1]
				_reload()
			"log":                         # log: open the log; log:<n>: copy its n-th line (0 = all)
				if bits.size() > 1:
					_copy_log(int(bits[1]) - 1)
				else:
					_log_open = true
					_log_card.visible = true
					_fill_log()
			"front":                       # front:r / front:l / front: (as drawn): as the «Спереди» buttons do
				var fv: String = bits[1] if bits.size() > 1 else ""
				for b: Button in _front_seg.get_children():
					if ["", "r", "l"][b.get_index()] == fv:
						b.emit_signal("pressed")
			"copy":                        # copy:<n> (0 = all): as the «Для ИИ» buttons do
				_copy_for_ai(int(bits[1]) - 1)
			"clip":                        # clip:<file>: what the clipboard holds now
				var cf := FileAccess.open(":".join(bits.slice(1)), FileAccess.WRITE)
				cf.store_string(DisplayServer.clipboard_get())
				cf.close()
			"side":                        # side:left: as the «Рука» buttons do
				_pick_side(bits[1])
			"elbow":
				_pick_elbow(bits[1] if bits.size() > 1 else "")
			"drag":
				_drag_to(_edited(), bits[1], Vector2(float(bits[2]), float(bits[3])))
			"hover":
				_hover = bits[1]
			"world":                       # world:<n>: switch to the n-th rubric of the list (0 = the first)
				_switch_world(cfg["worlds"][int(bits[1])])
			"press", "move", "release":    # press:x:y: a real mouse event, through the whole input pipeline
				var at := Vector2(float(bits[1]), float(bits[2]))
				var ev: InputEventMouse
				if bits[0] == "move":
					ev = InputEventMouseMotion.new()
					(ev as InputEventMouseMotion).button_mask = MOUSE_BUTTON_MASK_LEFT
				else:
					ev = InputEventMouseButton.new()
					(ev as InputEventMouseButton).button_index = MOUSE_BUTTON_LEFT
					(ev as InputEventMouseButton).pressed = bits[0] == "press"
				ev.position = get_viewport().get_screen_transform().affine_inverse() * at if false else at
				ev.global_position = ev.position
				Input.parse_input_event(ev)
			"dot":                         # dot:<name>:<file>: where that dot is now
				var pts2 := _dot_points(_edited())
				var df := FileAccess.open(":".join(bits.slice(2)), FileAccess.WRITE)
				df.store_string(JSON.stringify([(pts2[bits[1]] as Vector2).x, (pts2[bits[1]] as Vector2).y]))
				df.close()
			"fix":
				_fix()
			"still":
				still = true
				_set_life()
			"rest":
				pose_now = rest_pose()
				_apply_pose()
			"partner":                     # partner:<id>: the one on the right of the pair
				partner_id = bits[1]
				_reload()
			"dx":                          # dx:<share>: how far apart the pair stands
				_set_pair_dx(float(bits[1]))
				_reload()
			"stand":                       # stand:<k>:<x>: as dragging the ⇆ under that hero's feet to x (stage px)
				_stand_to(int(bits[1]), float(bits[2]))
			"edit":                        # edit:0 / edit:1: whose pose the dots change, as «Правлю позу» does
				_pick_edit(int(bits[1]))
			"save":                        # save:<id>: as «Сохранить» does
				_save_id.text = bits[1]
				_save_action()
			"select":                      # select:<n>: the n-th pose onto the hero (1 = the first)
				_select_pose(int(bits[1]) - 1)
			"where":                       # where:<file>: where the main hero's dots are (stage px)
				var pts := _dot_points(_edited())
				var out := {}
				for k: String in pts:
					out[k] = [(pts[k] as Vector2).x, (pts[k] as Vector2).y]
				var wf := FileAccess.open(":".join(bits.slice(1)), FileAccess.WRITE)
				wf.store_string(JSON.stringify(out))
				wf.close()
			"poses":
				_play_poses()
			"state":
				_write_state()
			"sizes":                       # sizes: the panel against the window, printed (a check of the layout)
				print("SIZES visible=%s panel=%s min=%s" % [get_viewport().get_visible_rect().size, _panel_bg.size, _panel_bg.get_combined_minimum_size()])
			"shot":
				get_viewport().get_texture().get_image().save_png(":".join(bits.slice(1)))
			"quit":
				get_tree().quit()
