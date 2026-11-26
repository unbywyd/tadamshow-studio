extends "res://stage.gd"
## THE WORKSHOP (docs: mechanics-tz.md, skill/reference/mechanics.md): look at the heroes and their mechanics, and
## make an action out of poses set by hand.
##
##   tadam workshop [hero]          (it writes the config and opens this scene: --config=<file.json>)
##
## The stage on the left, the panel on the right, two tabs:
##   МЕХАНИКА  every action of the library and of this world, by group, with a search; side, elbow, strength,
##             speed; a CLEAN switch by default (everything lets go and goes to rest first: motion.gd play_clean),
##             "поверх" layers it on what plays; slow (0.25x, 0.5x), pause, a step, a loop, the trail of the hands and
##             feet; the faults the hero check found in this action, with their numbers.
##   ПОЗЫ      dots on the hero: the hands, the feet, the pelvis (down / aside), the neck (the lean), the head (its
##             tilt); right click on a hand: palm / fist / back / edge / point; the wheel over a hand turns the
##             wrist; Shift + right click: where the elbow points. «Фикс» (F) keeps the pose in the list; every
##             pose has its way in (time, ease, hold); «Проиграть» plays the list as an action; «Сохранить» writes it
##             as an action of this world (actions/<id>.json), or of the core library with --core.
## One hero, all the world's heroes in a row (the same pose / action on all of them), or the proof bodies in a row.
## The files are the only truth: an action file changed on disk (by Claude) is read again at once; what is chosen
## and the pose list are written to <world>/.tadam/workshop/state.json for Claude, and `tadam workshop pose --fix`
## asks through cmd.json.

const MotionScript := preload("res://motion.gd")
const VIEW_NAMES := {"front": "спереди", "side_l": "влево", "side_r": "вправо", "back": "сзади"}
const GROUP_TITLES := {"pose": "Позы", "gesture": "Жесты", "body": "Тело", "move": "Перемещение", "feeling": "Чувства",
	"dance": "Танцы", "item": "Предметы", "fight": "Драка", "silly": "Дурачества", "music": "Музыка", "two": "Вдвоём"}
const LOOKS := ["auto", "palm", "fist", "back", "edge", "point"]
const LOOK_NAMES := {"auto": "сама", "palm": "ладонь", "fist": "кулак", "back": "тыльная", "edge": "ребро", "point": "палец"}
const ELBOWS := ["", "down", "up", "out", "in"]
const EASES := ["inout", "out", "in", "linear"]
const EASE_NAMES := ["плавно", "резко в начале", "резко в конце", "ровно"]
const DOT := 13.0
const REACH := 40.0
const INK := Color("2b6cb0")
const ACCENT := Color("c2351f")
const TRAIL := 120                  # steps of the trail
const HAND_PACE := 1.6              # arm lengths a second: the time a pose's way in gets by default

## kept across a reload of the scene (changing the hero or the row)
static var cfg: Dictionary = {}
static var row := "one"             # "one" | "all" | "proof"
static var hero_id := ""
static var tab := 0
static var poses: Array = []        # [{pose, time, ease, hold}]
static var pose_now: Dictionary = {}
static var chosen := ""             # the action chosen last
static var _cmd_seen := 0
static var still := false           # the idle life (breath, sway) off: a pose stands exactly still

var _side := "right"
var _elbow_say := ""
var _energy := 1.0
var _speed := 1.0
var speed := 1.0                    # the clock: 0.25 / 0.5 / 1
var paused := false
var _steps_wanted := 0
var _acc := 0.0
var _over_mode := false                 # "поверх": layered instead of a clean switch
var _loop := false
var _trails := false
var _pending: Dictionary = {}       # a line waiting for the clean switch to reach rest
var _idle := 0
var _trail: Dictionary = {}         # handle -> [points]
var _drag := ""
var _drag_off := Vector2.ZERO
var _sel := -1                      # the pose of the list being edited
var _stamp := ""
var _poll := 0.0
var _dirty_state := true

var _status: Label
var _faults: Label
var _playing_box: HBoxContainer
var _list: ItemList
var _list_ids: Array = []
var _search: LineEdit
var _pose_list: ItemList
var _pose_time: HSlider
var _pose_time_lbl: Label
var _pose_ease: OptionButton
var _pose_hold: CheckBox
var _save_id: LineEdit
var _save_title: LineEdit
var _dots: Node2D
var _tabs: TabContainer


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
	for i in heroes.size():
		var h: Dictionary = heroes[i]
		acts.append({"id": h["id"], "puppet": h["dir"], "x": (i + 1.0) / (heroes.size() + 1.0),
			"height": float(h.get("height", 0.36)) * (0.85 if heroes.size() > 2 else 1.0)})
	preset = {"floor": 0.84, "seconds": 99999, "actors": acts, "items": [], "script": []}
	camera_on = false
	super._ready()
	set_physics_process(true)
	_dots = Dots.new()
	_dots.ws = self
	_dots.z_index = 4000
	add_child(_dots)
	_build_panel()
	if pose_now.is_empty():
		pose_now = rest_pose()
	if tab == 1:
		_apply_pose.call_deferred()
	elif chosen != "" and actions().has(chosen):
		_play.call_deferred(chosen)
	_stamp = _actions_stamp()
	_set_life()
	_write_state()


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
		return proof
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


## The hero the dots and the faults are about: the chosen one, or the first of the row.
func _main() -> Actor:
	if actors.has(hero_id):
		return actors[hero_id]
	return actors.values()[0] if not actors.is_empty() else null


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


# ----------------------------------------------------------------------------- the panel

func _build_panel() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 20
	add_child(layer)
	var root := PanelContainer.new()
	root.position = Vector2(SIZE.x + 8, 8)
	root.size = Vector2(740, SIZE.y - 16)
	root.theme = _theme()
	root.add_theme_stylebox_override("panel", _flat(Color("f4efe6"), 0))
	layer.add_child(root)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 8)
	root.add_child(col)

	var pick := OptionButton.new()
	var all: Array = cfg.get("heroes", []) + cfg.get("proof", [])
	for h: Dictionary in all:
		pick.add_item(str(h.get("title", h["id"])))
	pick.select(maxi(all.map(func(h: Dictionary) -> String: return h["id"]).find(hero_id), 0))
	pick.item_selected.connect(func(i: int) -> void:
		hero_id = all[i]["id"]
		row = "one"
		_reload())
	var rows := OptionButton.new()
	for t: String in ["один", "все герои в ряд", "пробные тела в ряд"]:
		rows.add_item(t)
	rows.select(["one", "all", "proof"].find(row))
	rows.item_selected.connect(func(i: int) -> void:
		row = ["one", "all", "proof"][i]
		_reload())
	col.add_child(_row("Герой", [pick, rows]))
	var views: Array = []
	for v: Array in [["Спереди", "front"], ["Влево", "left"], ["Вправо", "right"], ["Сзади", "back"]]:
		views.append(_button(v[0], func() -> void:
			for id: String in actors:
				_command({"who": id, "turn": v[1]})))
	col.add_child(_row("Вид", views))

	# the clock
	var clock: Array = []
	for sp: float in [0.25, 0.5, 1.0]:
		clock.append(_button("%s×" % ("1" if sp == 1.0 else str(sp)), func() -> void:
			speed = sp
			_say("скорость %s×" % str(sp))))
	clock.append(_button("Пауза", func() -> void:
		paused = not paused
		_say("пауза" if paused else "идёт")))
	clock.append(_button("Шаг", func() -> void:
		paused = true
		_steps_wanted += 1))
	col.add_child(_row("Время", clock))
	var loop := CheckBox.new()
	loop.text = "по кругу"
	loop.toggled.connect(func(on: bool) -> void: _loop = on)
	var trails := CheckBox.new()
	trails.text = "след кистей и стоп"
	trails.toggled.connect(func(on: bool) -> void:
		_trails = on
		_trail.clear())
	var alive := CheckBox.new()
	alive.text = "дышит"
	alive.button_pressed = still == false
	alive.toggled.connect(func(on: bool) -> void:
		still = not on
		_set_life())
	col.add_child(_row("", [loop, trails, alive]))

	var tabs := TabContainer.new()
	_tabs = tabs
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	col.add_child(tabs)
	tabs.add_child(_mechanics_tab())
	tabs.add_child(_poses_tab())
	tabs.set_tab_title(0, "Механика")
	tabs.set_tab_title(1, "Позы")
	tabs.current_tab = tab
	tabs.tab_changed.connect(func(i: int) -> void:
		tab = i
		_dirty_state = true
		if i == 1:
			_apply_pose()
		else:
			_rest())

	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.text = "Нажмите действие" if tab == 0 else "Тяните точки на герое; «Фикс» — оставить позу"
	col.add_child(_status)


func _mechanics_tab() -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	var side := OptionButton.new()
	for sname: String in ["правая", "левая", "обе"]:
		side.add_item(sname)
	side.item_selected.connect(func(i: int) -> void: _side = ["right", "left", "both"][i])
	var elbow := OptionButton.new()
	for ename: String in ["локоть сам", "вниз", "вверх", "наружу", "внутрь"]:
		elbow.add_item(ename)
	elbow.item_selected.connect(func(i: int) -> void: _elbow_say = ELBOWS[i])
	box.add_child(_row("Сторона", [side, elbow]))
	box.add_child(_row("Сила", [_slider(0.5, 1.6, 1.0, func(v: float) -> void: _energy = v)]))
	box.add_child(_row("Скорость", [_slider(0.5, 1.6, 1.0, func(v: float) -> void: _speed = v)]))
	var over := CheckBox.new()
	over.text = "поверх (не отпускать прежнее)"
	over.toggled.connect(func(on: bool) -> void: _over_mode = on)
	box.add_child(_row("", [over, _button("В покой", _rest)]))
	_playing_box = HBoxContainer.new()
	box.add_child(_row("Играет", [_playing_box]))
	_search = LineEdit.new()
	_search.placeholder_text = "поиск: имя или название"
	_search.text_changed.connect(func(_t: String) -> void: _fill_list())
	box.add_child(_search)
	_list = ItemList.new()
	_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_list.item_clicked.connect(func(i: int, _at: Vector2, _b: int) -> void:
		if _list_ids[i] != "":
			_play(_list_ids[i]))
	box.add_child(_list)
	_faults = Label.new()
	_faults.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_faults.add_theme_color_override("font_color", ACCENT)
	box.add_child(_faults)
	_fill_list()
	return box


func _fill_list() -> void:
	if _list == null:
		return
	_list.clear()
	_list_ids.clear()
	var q := _search.text.strip_edges().to_lower() if _search != null else ""
	var by_group := {}
	for id: String in actions():
		var a: Dictionary = actions()[id]
		if id.begins_with("_") or id == "rest":
			continue
		var title := _title(a, id)
		if q != "" and not (q in id.to_lower() or q in title.to_lower()):
			continue
		by_group.get_or_add(a.get("group", "other"), []).append(id)
	for g: String in GROUP_TITLES.keys() + by_group.keys().filter(func(k: String) -> bool: return not GROUP_TITLES.has(k)):
		if not by_group.has(g):
			continue
		var gi := _list.add_item("— " + GROUP_TITLES.get(g, g) + " —")
		_list.set_item_selectable(gi, false)
		_list.set_item_custom_fg_color(gi, Color("8a7b66"))
		_list_ids.append("")
		var ids: Array = by_group[g]
		ids.sort()
		for id: String in ids:
			var mark := "   [рубрика]" if world_action_ids.has(id) else ""
			var i := _list.add_item("%s   (%s)%s" % [_title(actions()[id], id), id, mark])
			_list.set_item_tooltip(i, id)
			_list_ids.append(id)
			if id == chosen:
				_list.select(i)


static func _title(a: Dictionary, id: String) -> String:
	var t: Variant = a.get("title", id)
	if t is Dictionary:
		return str(t.get("ru", t.get("en", id)))
	return str(t)


func _poses_tab() -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	var hint := Label.new()
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.text = "Точки: кисти, стопы, таз (присесть, сдвинуться), шея (наклон), голова. Правый клик по кисти — вид кисти, колесо — поворот кисти, Shift + правый клик — куда локоть. F — фикс."
	box.add_child(hint)
	box.add_child(_row("", [_button("Фикс (F)", _fix), _button("Поза покоя", func() -> void:
		pose_now = rest_pose()
		_sel = -1
		_apply_pose()), _button("Проиграть", _play_poses), _button("Очистить", func() -> void:
		poses.clear()
		_sel = -1
		_fill_poses()
		_save_poses())]))
	_pose_list = ItemList.new()
	_pose_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_pose_list.item_selected.connect(func(i: int) -> void: _select_pose(i))
	box.add_child(_pose_list)
	box.add_child(_row("", [_button("Выше", func() -> void: _move_pose(-1)), _button("Ниже", func() -> void: _move_pose(1)),
		_button("Удалить", _delete_pose), _button("Заменить на текущую", func() -> void:
			if _sel >= 0:
				poses[_sel]["pose"] = pose_now.duplicate(true)
				_fill_poses()
				_save_poses())]))
	_pose_time_lbl = Label.new()
	_pose_time = _slider(0.1, 3.0, 0.5, func(v: float) -> void:
		_pose_time_lbl.text = "%.2f с" % v
		if _sel >= 0:
			poses[_sel]["time"] = snappedf(v, 0.05)
			_fill_poses()
			_save_poses())
	box.add_child(_row("Переход", [_pose_time, _pose_time_lbl]))
	_pose_ease = OptionButton.new()
	for e: String in EASE_NAMES:
		_pose_ease.add_item(e)
	_pose_ease.item_selected.connect(func(i: int) -> void:
		if _sel >= 0:
			poses[_sel]["ease"] = EASES[i]
			_fill_poses()
			_save_poses())
	_pose_hold = CheckBox.new()
	_pose_hold.text = "держать, пока не отпустят"
	_pose_hold.toggled.connect(func(on: bool) -> void:
		if _sel >= 0:
			poses[_sel]["hold"] = on
			_fill_poses()
			_save_poses())
	box.add_child(_row("", [_pose_ease, _pose_hold]))
	_save_id = LineEdit.new()
	_save_id.placeholder_text = "имя: латиница (my_wave)"
	_save_title = LineEdit.new()
	_save_title.placeholder_text = "название по-русски"
	box.add_child(_row("Действие", [_save_id, _save_title]))
	box.add_child(_button("Сохранить как действие " + ("общей библиотеки" if cfg.get("core", false) else "рубрики"), _save_action))
	_fill_poses()
	return box


static func _flat(colour: Color, radius: int) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = colour
	sb.set_corner_radius_all(radius)
	sb.content_margin_left = 10
	sb.content_margin_right = 10
	sb.content_margin_top = 5
	sb.content_margin_bottom = 5
	return sb


## Flat and light, like the stage: no borders, no shadows, no grey.
func _theme() -> Theme:
	var theme := Theme.new()
	theme.default_font_size = 22
	var ink := Color("2a2622")
	for kind: String in ["Button", "OptionButton"]:
		theme.set_stylebox("normal", kind, _flat(Color("e2d6bf"), 8))
		theme.set_stylebox("hover", kind, _flat(Color("d6c7a8"), 8))
		theme.set_stylebox("pressed", kind, _flat(Color("c4b08a"), 8))
		theme.set_stylebox("focus", kind, _flat(Color(0, 0, 0, 0), 8))
		for c: String in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
			theme.set_color(c, kind, ink)
	for c: String in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		theme.set_color(c, "CheckBox", ink)
	theme.set_stylebox("normal", "LineEdit", _flat(Color("fbf8f2"), 6))
	theme.set_stylebox("focus", "LineEdit", _flat(Color(0, 0, 0, 0), 6))
	theme.set_color("font_color", "LineEdit", ink)
	theme.set_color("font_placeholder_color", "LineEdit", Color("9a8d78"))
	theme.set_stylebox("panel", "ItemList", _flat(Color("fbf8f2"), 6))
	theme.set_stylebox("focus", "ItemList", _flat(Color(0, 0, 0, 0), 6))
	theme.set_stylebox("selected", "ItemList", _flat(Color("e2d6bf"), 4))
	theme.set_stylebox("selected_focus", "ItemList", _flat(Color("e2d6bf"), 4))
	theme.set_stylebox("hovered", "ItemList", _flat(Color("efe6d6"), 4))
	theme.set_color("font_color", "ItemList", ink)
	theme.set_color("font_selected_color", "ItemList", ink)
	theme.set_color("font_hovered_color", "ItemList", ink)
	theme.set_color("font_color", "Label", ink)
	theme.set_stylebox("panel", "TabContainer", _flat(Color("f4efe6"), 0))
	theme.set_stylebox("tab_selected", "TabContainer", _flat(Color("e2d6bf"), 8))
	theme.set_stylebox("tab_unselected", "TabContainer", _flat(Color("efe6d6"), 8))
	theme.set_stylebox("tab_hovered", "TabContainer", _flat(Color("d6c7a8"), 8))
	for c: String in ["font_selected_color", "font_unselected_color", "font_hovered_color"]:
		theme.set_color(c, "TabContainer", ink)
	theme.set_stylebox("panel", "PopupMenu", _flat(Color("f4efe6"), 6))
	theme.set_color("font_color", "PopupMenu", ink)
	theme.set_color("font_hover_color", "PopupMenu", ink)
	theme.set_stylebox("hover", "PopupMenu", _flat(Color("d6c7a8"), 4))
	theme.set_stylebox("slider", "HSlider", _flat(Color("d6c7a8"), 4))
	theme.set_stylebox("grabber_area", "HSlider", _flat(Color("b89f6d"), 4))
	theme.set_stylebox("grabber_area_highlight", "HSlider", _flat(Color("b89f6d"), 4))
	return theme


func _row(title: String, controls: Array) -> HBoxContainer:
	var row_box := HBoxContainer.new()
	if title != "":
		var l := Label.new()
		l.text = title
		l.custom_minimum_size = Vector2(110, 0)
		row_box.add_child(l)
	for c: Control in controls:
		c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row_box.add_child(c)
	return row_box


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
	s.custom_minimum_size = Vector2(0, 30)
	s.value_changed.connect(on_change)
	return s


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
	chosen = id
	_dirty_state = true
	_idle = 0
	_trail.clear()
	var lines: Array = []
	for aid: String in actors:
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
		lines.append(line)
	if _over_mode:
		for line: Dictionary in lines:
			_command(line)
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
	_say("%s  (%s)%s" % [_title(act, id), id, "   [рубрика]" if world_action_ids.has(id) else ""])
	_show_faults(id)


var _due_lines: Array = []


## The clean switch: every hero lets everything go and goes back to rest (motion.gd play_clean); the line waits.
func _let_go() -> void:
	for a: Actor in actors.values():
		_command({"who": a.id, "play": "off"})
		a.playing.clear()
		a.going = {}
		a.motion.play_clean({"id": "_rested", "phases": [{"time": 0.02}]})


func _rest() -> void:
	_pending = {}
	_let_go()
	chosen = ""
	_say("в покое")


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


## What plays now on the main hero, each with a button that lets it go.
func _refresh_playing() -> void:
	if _playing_box == null:
		return
	if not _due_lines.is_empty() and _pending.is_empty():
		var calm := true
		for a: Actor in actors.values():
			calm = calm and not a.motion.busy()
		if calm:
			for line: Dictionary in _due_lines:
				_command(line)
			_due_lines.clear()
	var a := _main()
	var ids: Array = []
	if a != null:
		for r in a.motion.runs:
			if not r.done and not str(r.id).begins_with("_") and r.id != "rest":
				ids.append(r)
	var sig := ",".join(ids.map(func(r) -> String: return str(r.id)))
	if _playing_box.get_meta("sig", "") == sig:
		return
	_playing_box.set_meta("sig", sig)
	for c in _playing_box.get_children():
		c.queue_free()
	if ids.is_empty():
		var l := Label.new()
		l.text = "ничего"
		_playing_box.add_child(l)
	for r in ids:
		_playing_box.add_child(_button(str(r.id) + "  ✕", func() -> void:
			for b: Actor in actors.values():
				for rr in b.motion.runs:
					if rr.id == r.id:
						b.motion.release(rr)))


## The faults the hero check found in this action on the main hero (heroes/<slug>/puppet/actions.json).
func _show_faults(id: String) -> void:
	if _faults == null:
		return
	_faults.text = ""
	var h := _hero_def(hero_id)
	var f: String = str(h.get("checks", ""))
	if f == "" or not FileAccess.file_exists(f):
		return
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(f))
	if not (data is Dictionary) or not data.get("actions", {}).has(id):
		return
	var lim: Dictionary = data.get("limits", {})
	var parts: Array = []
	for r: Dictionary in data["actions"][id].get("runs", []):
		for k: String in r.get("faults", {}):
			parts.append("%s: %s %s (порог %s)" % ["правая" if r.get("side", "right") == "right" else "левая", k,
				str(r["faults"][k]), str(lim.get(k, "?"))])
	if not parts.is_empty():
		_faults.text = "Брак (проверка героя): " + "; ".join(parts)


# ----------------------------------------------------------------------------- poses

## The rest pose of the main hero, in the action format (numbers only, nothing "rest").
func rest_pose() -> Dictionary:
	var a := _main()
	var p := {"legs": {"drop": 0.0, "shift": 0.0, "foot_l": [0.0, 0.0], "foot_r": [0.0, 0.0]}, "body": {"lean": 0.0}, "head": 0.0}
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
	var ph := pose_now.duplicate(true)
	ph["time"] = 0.12
	var hold := pose_now.duplicate(true)
	hold["time"] = 1.0
	hold["loop"] = true
	for a: Actor in actors.values():
		a.playing.clear()
		a.going = {}
		for r in a.motion.runs:
			if r.id != "_pose":
				r.done = true
				r.owned.clear()
		a.motion.runs = a.motion.runs.filter(func(r) -> bool: return not r.done)
		a.motion.play({"id": "_pose", "phases": [ph, hold]})
	_dirty_state = true


func _fix() -> void:
	var before: Dictionary = poses[-1]["pose"] if not poses.is_empty() else rest_pose()
	poses.append({"pose": pose_now.duplicate(true), "time": way_time(before, pose_now), "ease": "inout", "hold": false})
	_sel = poses.size() - 1
	_fill_poses()
	_save_poses()
	_say("поза %d зафиксирована" % poses.size())


## How long a hand (or a foot, or the body) needs from one pose to the next: the longest way at HAND_PACE.
static func way_time(a: Dictionary, b: Dictionary) -> float:
	var far := 0.0
	for ch: String in ["arm_l", "arm_r"]:
		if a.get(ch, null) is Dictionary and b.get(ch, null) is Dictionary:
			var p: Array = a[ch].get("at", [0, 0])
			var q: Array = b[ch].get("at", [0, 0])
			far = maxf(far, Vector2(p[0], p[1]).distance_to(Vector2(q[0], q[1])))
	if a.get("legs", null) is Dictionary and b.get("legs", null) is Dictionary:
		far = maxf(far, 1.5 * absf(float(a["legs"].get("drop", 0.0)) - float(b["legs"].get("drop", 0.0))))
		for f: String in ["foot_l", "foot_r"]:
			var p: Array = a["legs"].get(f, [0, 0])
			var q: Array = b["legs"].get(f, [0, 0])
			far = maxf(far, 1.5 * Vector2(p[0], p[1]).distance_to(Vector2(q[0], q[1])))
	if a.get("body", null) is Dictionary and b.get("body", null) is Dictionary:
		far = maxf(far, absf(float(a["body"].get("lean", 0.0)) - float(b["body"].get("lean", 0.0))) / 40.0)
	far = maxf(far, absf(float(a.get("head", 0.0)) - float(b.get("head", 0.0))) / 50.0)
	return snappedf(clampf(far / HAND_PACE + 0.15, 0.25, 2.0), 0.05)


func _fill_poses() -> void:
	if _pose_list == null:
		return
	_pose_list.clear()
	for i in poses.size():
		var p: Dictionary = poses[i]
		_pose_list.add_item("Поза %d   %.2f с, %s%s" % [i + 1, float(p["time"]), EASE_NAMES[EASES.find(p.get("ease", "inout"))],
			", держать" if p.get("hold", false) else ""])
	if _sel >= 0 and _sel < poses.size():
		_pose_list.select(_sel)


func _select_pose(i: int) -> void:
	_sel = i
	var p: Dictionary = poses[i]
	pose_now = (p["pose"] as Dictionary).duplicate(true)
	_pose_time.set_value_no_signal(float(p["time"]))
	_pose_time_lbl.text = "%.2f с" % float(p["time"])
	_pose_ease.select(EASES.find(p.get("ease", "inout")))
	_pose_hold.set_pressed_no_signal(bool(p.get("hold", false)))
	_apply_pose()
	_say("поза %d: правьте и нажмите «Заменить на текущую»" % (i + 1))


func _move_pose(d: int) -> void:
	if _sel < 0 or _sel + d < 0 or _sel + d >= poses.size():
		return
	var p: Variant = poses[_sel]
	poses.remove_at(_sel)
	_sel += d
	poses.insert(_sel, p)
	_fill_poses()
	_save_poses()


func _delete_pose() -> void:
	if _sel < 0:
		return
	poses.remove_at(_sel)
	_sel = mini(_sel, poses.size() - 1)
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
		_say("сначала зафиксируйте позы")
		return
	var act := poses_action(poses, "_poses", "позы", rest_pose())
	actions()["_poses"] = act
	for a: Actor in actors.values():
		a.motion.play_clean(act, {"side": "right", "duration": 1.5})
	_say("играют позы: %d" % poses.size())


func _save_action() -> void:
	var id := _save_id.text.strip_edges()
	if not RegEx.create_from_string("^[a-z][a-z0-9_]{0,39}$").search(id):
		_say("имя: латинские строчные буквы, цифры и _, с буквы")
		return
	if poses.is_empty():
		_say("сначала зафиксируйте позы")
		return
	var core: bool = cfg.get("core", false)
	var lib := ProjectSettings.globalize_path("res://actions")
	if not core and FileAccess.file_exists(lib.path_join(id + ".json")):
		_say("«%s» — имя из общей библиотеки: выберите другое" % id)
		return
	var dir: String = str(cfg.get("save_dir", ""))
	if dir == "":
		_say("некуда сохранять: откройте мастерскую в папке мира")
		return
	DirAccess.make_dir_recursive_absolute(dir)
	var path := dir.path_join(id + ".json")
	var title := _save_title.text.strip_edges()
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
	reload_actions()
	_stamp = _actions_stamp()
	_fill_list()
	_say("сохранено: %s%s. Проверка: tadam action check %s --proof" % [path, "  (общая библиотека: меняется у всех миров после выпуска)" if core else "", id])


# ----------------------------------------------------------------------------- the dots

func _dot_points(a: Actor) -> Dictionary:
	var p: Puppet = a.puppet
	var out := {"hand_l": p.handle_position("hand_l"), "hand_r": p.handle_position("hand_r"),
		"foot_l": p.handle_position("foot_l"), "foot_r": p.handle_position("foot_r"),
		"body": p.body_position()}
	if p.parts.has("head"):
		var neck: Vector2 = p.parts["head"].node.global_position
		out["neck"] = neck
		out["head"] = p.parts["head"].node.to_global(p.parts["head"].center)
	return out


func _draw_dots(canvas: Node2D) -> void:
	var a := _main()
	if a == null:
		return
	if _trails:
		for h: String in _trail:
			var tr: Array = _trail[h]
			for i in range(1, tr.size()):
				canvas.draw_line(tr[i - 1], tr[i], Color(ACCENT, float(i) / tr.size() * 0.8), 3.0, true)
	if tab != 1:
		return
	var pts := _dot_points(a)
	for k: String in pts:
		var at: Vector2 = pts[k]
		var fill := Color(INK, 0.85 if _drag == k else 0.5)
		if k == "neck" or k == "head":
			fill = Color(ACCENT, 0.85 if _drag == k else 0.5)
		canvas.draw_circle(at, DOT, fill, true, -1.0, true)
		canvas.draw_circle(at, DOT, Color.WHITE, false, 3.0, true)
	for ch: String in ["arm_l", "arm_r"]:
		var arm: Dictionary = pose_now.get(ch, {})
		if arm.has("look") or arm.has("elbow") or arm.has("wrist"):
			var note: Array = []
			if arm.has("look"):
				note.append(LOOK_NAMES.get(arm["look"], arm["look"]))
			if arm.has("wrist"):
				note.append("%d°" % int(arm["wrist"]))
			if arm.has("elbow"):
				note.append("локоть " + str(arm["elbow"]))
			canvas.draw_string(ThemeDB.fallback_font, pts["hand_" + ch.right(1)] + Vector2(18, -14), ", ".join(note),
				HORIZONTAL_ALIGNMENT_LEFT, -1, 20, INK)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_F and tab == 1:
			_fix()
		elif event.keycode == KEY_SPACE:
			paused = not paused
		elif event.keycode == KEY_PERIOD:
			paused = true
			_steps_wanted += 1
		return
	if tab != 1:
		return
	var a := _main()
	if a == null:
		return
	var m := get_global_mouse_position()
	if event is InputEventMouseButton:
		var e := event as InputEventMouseButton
		var k := _pick(a, m)
		if e.button_index == MOUSE_BUTTON_LEFT:
			if e.pressed and k != "":
				_drag = k
				_drag_off = _dot_points(a)[k] - m
			elif not e.pressed:
				_drag = ""
		elif e.pressed and e.button_index == MOUSE_BUTTON_RIGHT and k.begins_with("hand"):
			var ch := "arm_" + k.right(1)
			var arm: Dictionary = pose_now[ch]
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
		elif e.pressed and e.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN] and k.begins_with("hand"):
			var arm2: Dictionary = pose_now["arm_" + k.right(1)]
			var w := clampf(float(arm2.get("wrist", 0.0)) + (5.0 if e.button_index == MOUSE_BUTTON_WHEEL_UP else -5.0), -80.0, 80.0)
			if absf(w) < 0.5:
				arm2.erase("wrist")
			else:
				arm2["wrist"] = w
			_apply_pose()
	elif event is InputEventMouseMotion and _drag != "":
		_drag_to(a, _drag, m + _drag_off)


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
		var v2: Vector2 = to - (_dot_points(a)["neck"] as Vector2)
		pose_now["head"] = snappedf(clampf(rad_to_deg(atan2(v2.x, -v2.y)) - float(pose_now["body"].get("lean", 0.0)), -35.0, 35.0), 1.0)
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
		_fill_list()
		if tab == 0 and chosen != "" and actions().has(chosen):
			_play(chosen)
			_say("файл изменился: %s играет заново" % chosen)
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
					if tab == 1:
						_fix()
				"pose":
					if c.get("pose", null) is Dictionary:
						pose_now = c["pose"]
						_apply_pose()
				"play":
					if actions().has(str(c.get("action", ""))):
						_play(str(c["action"]))
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
	var st := {"hero": hero_id, "row": row, "tab": ["mechanics", "poses"][tab], "action": chosen,
		"view": a.view if a != null else "front", "pose": pose_now, "poses": poses.size(), "pose_selected": _sel + 1,
		"cmd_seen": _cmd_seen, "at": Time.get_datetime_string_from_system(false, true)}
	var f := FileAccess.open(dir.path_join("state.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify(st, " ", false) + "\n")
	f.close()


# ----------------------------------------------------------------------------- checks of the window itself

## WORKSHOP_SEQ="tab:1@20,drag:hand_r:560:420@40,fix@80,shot:<file>@120": steps it by itself (tests), quits after.
var _frames := 0
var _seq: Array = []


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
				_tabs.current_tab = int(bits[1])
			"play":
				_play(bits[1])
			"drag":
				var a := _main()
				_drag_to(a, bits[1], Vector2(float(bits[2]), float(bits[3])))
			"fix":
				_fix()
			"still":
				still = true
				_set_life()
			"rest":
				pose_now = rest_pose()
				_apply_pose()
			"select":                      # select:<n>: the n-th pose of the list onto the hero (1 = the first)
				_select_pose(int(bits[1]) - 1)
			"where":                       # where:<file>: where the main hero's dots are (stage px)
				var pts := _dot_points(_main())
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
			"shot":
				get_viewport().get_texture().get_image().save_png(":".join(bits.slice(1)))
			"quit":
				get_tree().quit()
