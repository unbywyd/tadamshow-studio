extends RefCounted
## EFFECTS AND TITLES of a scene (docs/framework-tz.md 6.7). Script lines:
##   {"who": "loaf", "say": "Привет!", "for": 2.5}   a speech bubble over that hero's head (it follows the head)
##   {"subtitle": "текст", "for": 3}                 a line of text at the bottom of the picture
##   {"title": "Глава первая", "for": 2.5}           a big title in the middle, fading in and out
##   {"flash": 0.25}                                 the picture goes white and back in that many seconds
##   {"confetti": 2.0}                               confetti falls over the whole picture for that long
##   {"who": "loaf", "stars": 1.5}                   little stars circle the hero's head (also by itself after a
##                                                   blow: the action "get_hit")
## All of it is drawn over the picture, after the colour grade: titles and bubbles keep their own colours. Flat and
## matte: no outlines, no drop shadows; the type big enough to read on a phone.

const INK := Color(0.16, 0.14, 0.12)
const PAPER := Color(0.99, 0.97, 0.92)
const FONT_NAMES := ["Segoe UI", "Arial", "Helvetica", "Noto Sans", "DejaVu Sans"]

var layer: CanvasLayer
var size := Vector2(720, 1280)
var font: Font
var _items: Array = []          # [{kind, node, from, until, ...}]
var _flash: ColorRect
var _flash_t := 0.0
var _flash_len := 0.0


func setup(host: Node, screen: Vector2) -> void:
	size = screen
	layer = CanvasLayer.new()
	layer.layer = 60                   # (over the colour grade, layer 50)
	host.add_child(layer)
	var sf := SystemFont.new()
	sf.font_names = PackedStringArray(FONT_NAMES)
	sf.font_weight = 600
	font = sf
	_flash = ColorRect.new()
	_flash.size = screen
	_flash.set_anchors_preset(Control.PRESET_FULL_RECT)      # (the whole window, however it is resized)
	_flash.color = Color(1, 1, 1, 0)
	_flash.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(_flash)


## A bubble or a label: a flat rounded panel with text in it.
func _panel(text: String, font_size: int, bg: Color, fg: Color, max_w: float) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = bg
	sb.set_corner_radius_all(int(font_size * 0.9))
	sb.content_margin_left = font_size * 0.8
	sb.content_margin_right = font_size * 0.8
	sb.content_margin_top = font_size * 0.45
	sb.content_margin_bottom = font_size * 0.5
	p.add_theme_stylebox_override("panel", sb)
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", font)
	l.add_theme_font_size_override("font_size", font_size)
	l.add_theme_color_override("font_color", fg)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(minf(max_w, font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x + 4.0), 0.0)
	p.add_child(l)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return p


## A script line. `head`: Callable(hero id) -> its head's top middle on the screen (or null). Returns true if the
## line was about effects only.
func command(line: Dictionary, n: int, head: Callable) -> void:
	var t := n / 60.0
	if line.has("say") and line.has("who"):
		var p := _panel(str(line["say"]), int(size.x * 0.045), PAPER, INK, size.x * 0.62)
		var tail := Polygon2D.new()
		tail.color = PAPER
		layer.add_child(tail)
		layer.add_child(p)
		_items.append({"kind": "say", "node": p, "tail": tail, "who": line["who"], "from": t,
			"until": t + float(line.get("for", 2.5)), "head": head})
	if line.has("subtitle"):
		var p2 := _panel(str(line["subtitle"]), int(size.x * 0.042), Color(0.1, 0.09, 0.08, 0.72), PAPER, size.x * 0.86)
		layer.add_child(p2)
		_items.append({"kind": "sub", "node": p2, "from": t, "until": t + float(line.get("for", 3.0))})
	if line.has("title"):
		var l := Label.new()
		l.text = str(line["title"])
		l.add_theme_font_override("font", font)
		l.add_theme_font_size_override("font_size", int(size.x * 0.09))
		l.add_theme_color_override("font_color", PAPER)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.size = Vector2(size.x * 0.86, size.y * 0.3)
		l.position = Vector2(size.x * 0.07, size.y * 0.35)
		var band := ColorRect.new()
		band.color = Color(0.1, 0.09, 0.08, 0.55)
		band.size = Vector2(size.x, size.y * 0.22)
		band.position = Vector2(0.0, size.y * 0.39)
		band.mouse_filter = Control.MOUSE_FILTER_IGNORE
		layer.add_child(band)
		layer.add_child(l)
		_items.append({"kind": "title", "node": l, "band": band, "from": t, "until": t + float(line.get("for", 2.5))})
	if line.has("flash"):
		_flash_len = maxf(float(line["flash"]), 0.05)
		_flash_t = 0.0
	if line.has("confetti"):
		var c := _confetti()
		layer.add_child(c)
		_items.append({"kind": "confetti", "node": c, "from": t, "until": t + float(line["confetti"]), "stop": t + float(line["confetti"])})
	if line.has("stars") and line.has("who"):
		stars(str(line["who"]), float(line["stars"]), n, head)


## Little stars round a hero's head (after a blow).
func stars(who: String, sec: float, n: int, head: Callable) -> void:
	var t := n / 60.0
	var root := Node2D.new()
	layer.add_child(root)
	for i in 5:
		var s := Polygon2D.new()
		var pts := PackedVector2Array()
		var r: float = size.x * 0.016
		for k in 10:
			var rr: float = r if k % 2 == 0 else r * 0.45
			pts.append(Vector2(cos(-PI / 2.0 + k * PI / 5.0), sin(-PI / 2.0 + k * PI / 5.0)) * rr)
		s.polygon = pts
		s.color = Color(1.0, 0.85, 0.25) if i % 2 == 0 else Color(1.0, 0.97, 0.8)
		root.add_child(s)
	_items.append({"kind": "stars", "node": root, "who": who, "from": t, "until": t + sec, "head": head})


func step(n: int) -> void:
	var t := n / 60.0
	if layer.get_viewport() != null:
		size = layer.get_viewport().get_visible_rect().size     # (the window may have been resized)
	if _flash_len > 0.0:
		_flash_t += 1.0 / 60.0
		var u: float = _flash_t / _flash_len
		_flash.color.a = clampf(1.0 - u, 0.0, 1.0) * 0.9 if u < 1.0 else 0.0
		if u >= 1.0:
			_flash_len = 0.0
	var keep: Array = []
	for it: Dictionary in _items:
		var node: Node = it["node"]
		if t >= float(it["until"]) + (2.5 if it["kind"] == "confetti" else 0.0):
			node.queue_free()
			if it.has("tail"):
				(it["tail"] as Node).queue_free()
			if it.has("band"):
				(it["band"] as Node).queue_free()
			continue
		keep.append(it)
		# fades in and out over a fifth of a second
		var a: float = clampf(minf((t - float(it["from"])) / 0.2, (float(it["until"]) - t) / 0.2), 0.0, 1.0)
		match it["kind"]:
			"say":
				var p: PanelContainer = node
				var h: Variant = (it["head"] as Callable).call(it["who"])
				if h == null:
					p.visible = false
					(it["tail"] as Polygon2D).visible = false
					continue
				var top: Vector2 = h
				var sz: Vector2 = p.get_combined_minimum_size()
				var at := Vector2(clampf(top.x - sz.x * 0.5, 12.0, size.x - sz.x - 12.0), maxf(top.y - sz.y - size.x * 0.05, 12.0))
				p.position = at
				p.size = sz
				p.modulate.a = a
				var tail: Polygon2D = it["tail"]
				var base_x: float = clampf(top.x, at.x + sz.x * 0.2, at.x + sz.x * 0.8)
				var w: float = size.x * 0.025
				tail.polygon = PackedVector2Array([Vector2(base_x - w, at.y + sz.y - 2.0), Vector2(base_x + w, at.y + sz.y - 2.0),
						Vector2(lerpf(base_x, top.x, 0.6), at.y + sz.y + size.x * 0.035)])
				tail.modulate.a = a
			"sub":
				var p2: PanelContainer = node
				var sz2: Vector2 = p2.get_combined_minimum_size()
				p2.size = sz2
				p2.position = Vector2((size.x - sz2.x) * 0.5, size.y * 0.88 - sz2.y)
				p2.modulate.a = a
			"title":
				var tl: Label = node
				var band: ColorRect = it["band"]
				tl.size = Vector2(size.x * 0.86, size.y * 0.3)
				tl.position = Vector2(size.x * 0.07, size.y * 0.35)
				band.size = Vector2(size.x, size.y * 0.22)
				band.position = Vector2(0.0, size.y * 0.39)
				tl.modulate.a = a
				band.modulate.a = a
			"confetti":
				(node as CPUParticles2D).emitting = t < float(it["stop"])
			"stars":
				var h2: Variant = (it["head"] as Callable).call(it["who"])
				var root: Node2D = node
				root.visible = h2 != null
				if h2 == null:
					continue
				var c: Vector2 = h2
				for i in root.get_child_count():
					var ang: float = TAU * (t * 0.9 + i / 5.0)
					var s: Polygon2D = root.get_child(i)
					s.position = c + Vector2(cos(ang) * size.x * 0.07, sin(ang) * size.x * 0.018 - size.x * 0.01)
					s.rotation = t * 4.0 + i
					s.modulate.a = a
	_items = keep


func _confetti() -> CPUParticles2D:
	var p := CPUParticles2D.new()
	p.use_fixed_seed = true
	p.seed = 4242
	p.amount = 140
	p.lifetime = 3.2
	p.position = Vector2(size.x * 0.5, -size.y * 0.03)
	p.emission_shape = CPUParticles2D.EMISSION_SHAPE_RECTANGLE
	p.emission_rect_extents = Vector2(size.x * 0.55, 4.0)
	p.direction = Vector2(0.0, 1.0)
	p.spread = 20.0
	p.gravity = Vector2(0.0, size.y * 0.12)
	p.initial_velocity_min = size.y * 0.08
	p.initial_velocity_max = size.y * 0.2
	p.angular_velocity_min = -300.0
	p.angular_velocity_max = 300.0
	var g := GradientTexture2D.new()
	var gr := Gradient.new()
	gr.set_color(0, Color.WHITE)
	gr.set_color(1, Color.WHITE)
	g.gradient = gr
	g.width = 8
	g.height = 5
	p.texture = g
	p.scale_amount_min = size.x / 720.0 * 1.6
	p.scale_amount_max = size.x / 720.0 * 2.4
	var cols := Gradient.new()
	cols.offsets = PackedFloat32Array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
	cols.colors = PackedColorArray([Color(0.93, 0.33, 0.3), Color(0.98, 0.78, 0.25), Color(0.36, 0.7, 0.45),
			Color(0.3, 0.55, 0.85), Color(0.75, 0.45, 0.8), Color(0.93, 0.33, 0.3)])
	p.color_initial_ramp = cols
	p.emitting = true
	return p
