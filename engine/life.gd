extends RefCounted
## The LIVING BACKGROUND (docs/framework-tz.md 6.2): no video is made. Life is put together from ready behaviours,
## each hung on a set piece of the background (a piece cut out of the picture: tools/cut_piece.py) or on a place in
## it. scene.json:
##   "life": [ {"kind": ..., ...}, ... ]
## Places and sizes are shares of the WORLD (as "pieces" are): "at": [x, y], "rect": [x, y, w, h].
##   sway     a piece swings about its pivot: "piece", "pivot": [u, v] (share of the piece, default its top middle),
##            "deg": 4, "period": 3.0                                                  - a lamp on its cord, a sign, laundry
##   bob      a piece rises and sinks (and tilts a little): "piece", "amp": 0.01, "period": 2.5, "deg": 2   - a boat, a float
##   spin     a piece turns round: "piece", "pivot" (default its middle), "rpm": 6        - a wheel, a mill
##   drift    a piece floats sideways over the whole world and comes back from the other side: "piece", "speed": 0.01
##            (world widths a second)                                                  - clouds, fog, the moon
##   glow     a soft light over a place that flickers: "at", "radius": 0.06, "color": [1, 0.8, 0.45], "energy": 0.5,
##            "flicker": 0.3 (how much it wavers), "rate": 6, "on": piece id (it moves with that piece) - fire, a lamp,
##            windows, stars
##   blink    a piece goes out for a moment now and then: "piece", "every": 4.0, "for": 0.15 - eyes in the dark, a light
##   particles "type": smoke | steam | dust | fireflies | rain | snow | leaves | sparks, "at" (a point it comes from) or
##            "rect" (a place it fills), "amount", "color", "size" (share of the world width)
##   ripple   the picture wavers inside "rect": "amp": 0.003, "speed": 1.0               - water, heat over a stove
## Every element may say "base": y (share of the world height: where it stands on the ground, sorted in depth with the
## heroes, as pieces are) or "front": true (in front of everyone). Without either it is part of the background.
## A piece that MOVES needs the background under it painted clean (tools/cut_piece.py --moves writes "under"), or the
## piece's own painted place shows beside it as it swings.
##
## Nothing here is random at run time: every wave is a sum of sines of the step number, particles have a fixed seed,
## so a scene films the same frame for frame.

const DT := 1.0 / 60.0

var world := Vector2(720, 1280)
var elements: Array = []          # [{kind, spec, node, ...}]
var layers: Array = []            # [{layer: CanvasLayer, z: float}] for the stage to sort with the heroes
var warnings: Array = []

static var _ripple_shader: Shader
static var _soft: Texture2D


## `pieces`: id -> {"holder": Node2D, "sprite": Sprite2D, "rect": Rect2} (stage.gd _add_piece). `back`: the
## background's own layer. `ground`: Callable(Vector2 world point) -> z (the depth of a place on the ground).
func setup(specs: Array, world_size: Vector2, pieces: Dictionary, back: CanvasLayer, host: Node, ground: Callable) -> void:
	world = world_size
	var seed_no := 1
	for spec: Dictionary in specs:
		var kind: String = spec.get("kind", "")
		var parent: Node = back
		if spec.get("front", false) or spec.has("base"):
			var l := CanvasLayer.new()
			host.add_child(l)
			var z: float = -INF if spec.get("front", false) else float(ground.call(Vector2(_at(spec).x, world.y * float(spec["base"]))))
			layers.append({"layer": l, "z": z})
			parent = l
		var e := {"kind": kind, "spec": spec}
		match kind:
			"sway", "bob", "spin", "drift", "blink":
				var pc: Variant = pieces.get(spec.get("piece", ""), null)
				if pc == null:
					warnings.append("life: %s needs a piece, there is no '%s'" % [kind, spec.get("piece", "")])
					continue
				e["piece"] = pc
				var r: Rect2 = pc["rect"]
				var pv: Array = spec.get("pivot", [0.5, 0.0] if kind == "sway" else [0.5, 0.5])
				_repivot(pc, r.position + r.size * Vector2(float(pv[0]), float(pv[1])))
				e["home"] = (pc["holder"] as Node2D).position
			"glow":
				var s := Sprite2D.new()
				s.texture = _soft_texture()
				var mat := CanvasItemMaterial.new()
				mat.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
				s.material = mat
				var c: Array = spec.get("color", [1.0, 0.8, 0.45])
				e["color"] = Color(c[0], c[1], c[2])
				var radius: float = float(spec.get("radius", 0.06)) * world.x
				s.scale = Vector2.ONE * (2.0 * radius / s.texture.get_width())
				s.position = _at(spec)
				parent.add_child(s)
				e["node"] = s
				e["on"] = pieces.get(spec.get("on", ""), null)
				if e["on"] != null:
					# (it keeps its place ON the piece: where it is in the piece's own frame)
					e["local"] = s.position - (e["on"]["holder"] as Node2D).position
			"particles":
				var p := _particles(spec, seed_no)
				seed_no += 1
				parent.add_child(p)
				e["node"] = p
			"ripple":
				var r := _rect(spec)
				var cr := ColorRect.new()
				cr.position = r.position
				cr.size = r.size
				var sm := ShaderMaterial.new()
				sm.shader = _ripple()
				sm.set_shader_parameter("amp", float(spec.get("amp", 0.003)))
				sm.set_shader_parameter("freq", float(spec.get("freq", 60.0)))
				sm.set_shader_parameter("speed", float(spec.get("speed", 1.0)))
				cr.material = sm
				parent.add_child(cr)
				e["node"] = cr
			_:
				warnings.append("life: no such behaviour '%s'" % kind)
				continue
		elements.append(e)
	if elements.size() < 3:
		warnings.append("life: %d living elements, a scene wants 3 or more (docs/framework-tz.md 6.2)" % elements.size())


## One step: everything is a function of the step number.
func step(n: int) -> void:
	var t: float = n * DT
	for e: Dictionary in elements:
		var spec: Dictionary = e["spec"]
		var ph: float = float(spec.get("phase", 0.0))
		match e["kind"]:
			"sway":
				var period: float = float(spec.get("period", 3.0))
				var w: float = TAU * (t / period + ph)
				# a swing with a little wind in it: never quite the same twice
				var a: float = sin(w) + 0.25 * sin(2.3 * w + 1.1) + 0.12 * sin(0.37 * w + 2.0)
				(e["piece"]["holder"] as Node2D).rotation = deg_to_rad(float(spec.get("deg", 4.0))) * a / 1.25
			"bob":
				var w2: float = TAU * (t / float(spec.get("period", 2.5)) + ph)
				var h: Node2D = e["piece"]["holder"]
				h.position = e["home"] + Vector2(0.0, float(spec.get("amp", 0.01)) * world.y * sin(w2))
				h.rotation = deg_to_rad(float(spec.get("deg", 2.0))) * sin(w2 + 0.9)
			"spin":
				(e["piece"]["holder"] as Node2D).rotation = TAU * float(spec.get("rpm", 6.0)) / 60.0 * t + TAU * ph
			"drift":
				# (its middle goes from just past the right edge round to just before the left one, and on)
				var h2: Node2D = e["piece"]["holder"]
				var half: float = 0.5 * (e["piece"]["rect"] as Rect2).size.x
				var x: float = fposmod(e["home"].x + half + float(spec.get("speed", 0.01)) * world.x * t, world.x + 2.0 * half) - half
				h2.position = Vector2(x, e["home"].y)
			"blink":
				var every: float = float(spec.get("every", 4.0))
				var u: float = fposmod(t + ph * every, every)
				(e["piece"]["sprite"] as Sprite2D).visible = u > float(spec.get("for", 0.15))
			"glow":
				var f: float = float(spec.get("flicker", 0.3))
				var rate: float = float(spec.get("rate", 6.0))
				var wave: float = 0.5 * sin(rate * t + 7.0 * ph) + 0.3 * sin(rate * 2.71 * t + 1.3) + 0.2 * sin(rate * 0.43 * t + 4.0)
				var dip: float = 1.0 - f * 0.5 * (1.0 + wave)
				var s: Sprite2D = e["node"]
				s.modulate = Color(e["color"].r, e["color"].g, e["color"].b, clampf(float(spec.get("energy", 0.5)) * dip, 0.0, 1.0))
				if e.get("on") != null:
					var holder: Node2D = e["on"]["holder"]
					s.position = holder.position + e["local"].rotated(holder.rotation)
			"ripple":
				((e["node"] as ColorRect).material as ShaderMaterial).set_shader_parameter("t", t)


## The places IN FRONT of the heroes that something living takes (a glow, smoke, a piece drawn in front of everyone):
## a face must not be behind them (docs/framework-tz.md 6.2). Rain and snow fall over everything and do not count.
func front_boxes() -> Array:
	var out: Array = []
	for e: Dictionary in elements:
		var spec: Dictionary = e["spec"]
		if not spec.get("front", false) or (e["kind"] == "particles" and spec.get("type", "") in ["rain", "snow"]):
			continue
		if e.has("piece"):
			var h: Node2D = e["piece"]["holder"]
			var r: Rect2 = e["piece"]["rect"]
			out.append([spec.get("piece", e["kind"]), Rect2(h.position + (e["piece"]["sprite"] as Sprite2D).position, r.size)])
		elif spec.has("rect"):
			out.append([e["kind"], _rect(spec)])
		else:
			var rad: float = float(spec.get("radius", 0.05)) * world.x
			out.append([e["kind"], Rect2(_at(spec) - Vector2(rad, rad), Vector2(2.0 * rad, 2.0 * rad))])
	return out


## Where a place is: "at" or the middle of "rect" (world px).
func _at(spec: Dictionary) -> Vector2:
	if spec.has("at"):
		return Vector2(float(spec["at"][0]), float(spec["at"][1])) * world
	return _rect(spec).get_center()


func _rect(spec: Dictionary) -> Rect2:
	var r: Array = spec.get("rect", [0.0, 0.0, 1.0, 1.0])
	return Rect2(float(r[0]) * world.x, float(r[1]) * world.y, float(r[2]) * world.x, float(r[3]) * world.y)


## The piece turns about `pivot` (world px) from now on: its holder stands there, the picture keeps its place.
static func _repivot(pc: Dictionary, pivot: Vector2) -> void:
	var h: Node2D = pc["holder"]
	var s: Sprite2D = pc["sprite"]
	var r: Rect2 = pc["rect"]
	h.position = pivot
	s.position = r.position - pivot


static func _soft_texture() -> Texture2D:
	if _soft == null:
		var g := Gradient.new()
		g.set_color(0, Color(1, 1, 1, 1))
		g.set_color(1, Color(1, 1, 1, 0))
		g.add_point(0.35, Color(1, 1, 1, 0.55))
		var gt := GradientTexture2D.new()
		gt.gradient = g
		gt.fill = GradientTexture2D.FILL_RADIAL
		gt.fill_from = Vector2(0.5, 0.5)
		gt.fill_to = Vector2(1.0, 0.5)
		gt.width = 128
		gt.height = 128
		_soft = gt
	return _soft


static var _streak: Texture2D


static func _streak_texture() -> Texture2D:
	if _streak == null:
		var g := Gradient.new()
		g.set_color(0, Color(1, 1, 1, 0))
		g.set_color(1, Color(1, 1, 1, 0))
		g.add_point(0.5, Color(1, 1, 1, 1))
		var gt := GradientTexture2D.new()
		gt.gradient = g
		gt.fill_from = Vector2(0.5, 0.0)
		gt.fill_to = Vector2(0.5, 1.0)
		gt.width = 10
		gt.height = 96
		_streak = gt
	return _streak


static var _leaf: Texture2D


## A leaf: a pointed oval with a darker middle vein, white (it is coloured by the particles' colour).
static func _leaf_texture() -> Texture2D:
	if _leaf == null:
		var w := 48
		var h := 24
		var im := Image.create(w, h, false, Image.FORMAT_RGBA8)
		for y in h:
			for x in w:
				var u: float = (x + 0.5) / w * 2.0 - 1.0          # -1..1 along the leaf
				var v: float = (y + 0.5) / h * 2.0 - 1.0          # -1..1 across it
				var half: float = pow(maxf(1.0 - u * u, 0.0), 0.8)  # pointed at both ends
				var d: float = absf(v) - half
				var a: float = clampf(0.5 - d * h * 0.5, 0.0, 1.0)
				var vein: float = 0.78 if absf(v) < 0.08 and absf(u) < 0.85 else 1.0
				im.set_pixel(x, y, Color(vein, vein, vein, a))
		_leaf = ImageTexture.create_from_image(im)
	return _leaf


static func _ripple() -> Shader:
	if _ripple_shader == null:
		_ripple_shader = Shader.new()
		_ripple_shader.code = """
shader_type canvas_item;
uniform sampler2D screen_tex : hint_screen_texture, filter_linear;
uniform float amp = 0.003;
uniform float freq = 60.0;
uniform float speed = 1.0;
uniform float t = 0.0;
void fragment() {
	// fades out towards the rect's edges: no seam where the wavering stops
	float edge = smoothstep(0.0, 0.2, UV.x) * smoothstep(1.0, 0.8, UV.x) * smoothstep(0.0, 0.25, UV.y) * smoothstep(1.0, 0.75, UV.y);
	vec2 uv = SCREEN_UV;
	uv.x += edge * amp * sin(uv.y * freq + t * speed * 6.2832);
	uv.y += edge * amp * 0.4 * sin(uv.x * freq * 0.7 + t * speed * 4.1);
	COLOR = texture(screen_tex, uv);
}
"""
	return _ripple_shader


## A particle system by its kind. Sizes are shares of the world's width; everything slow and soft (a fairy tale,
## not a storm), and already going at the first frame.
func _particles(spec: Dictionary, seed_no: int) -> CPUParticles2D:
	var p := CPUParticles2D.new()
	var kind: String = spec.get("type", "dust")
	p.texture = _soft_texture()
	p.use_fixed_seed = true
	p.seed = seed_no * 7919
	p.local_coords = false
	var px: float = world.x / 128.0                    # the texture is 128 px: scale 1 = a 128 px blob
	var size: float = float(spec.get("size", 0.0))
	if spec.has("rect"):
		var r := _rect(spec)
		p.position = r.get_center()
		p.emission_shape = CPUParticles2D.EMISSION_SHAPE_RECTANGLE
		p.emission_rect_extents = r.size * 0.5
	else:
		p.position = _at(spec)
		p.emission_shape = CPUParticles2D.EMISSION_SHAPE_SPHERE
		p.emission_sphere_radius = 0.006 * world.x
	var c: Array = spec.get("color", [])
	var ramp := Gradient.new()
	match kind:
		"smoke", "steam":
			var steam: bool = kind == "steam"
			p.amount = int(spec.get("amount", 18 if steam else 24))
			p.lifetime = 2.2 if steam else 5.0
			p.direction = Vector2(0.0, -1.0)
			p.spread = 12.0
			p.gravity = Vector2(0.006 * world.x, -0.004 * world.x)          # rises, and the air takes it aside
			p.initial_velocity_min = 0.025 * world.x
			p.initial_velocity_max = 0.04 * world.x
			p.scale_amount_min = (size if size > 0.0 else 0.025) * world.x / 128.0
			p.scale_amount_max = p.scale_amount_min * 1.4
			var grow := Curve.new()
			grow.add_point(Vector2(0.0, 0.5))
			grow.add_point(Vector2(1.0, 2.6))
			p.scale_amount_curve = grow
			var col := Color(c[0], c[1], c[2]) if c.size() >= 3 else (Color(1, 1, 1) if steam else Color(0.75, 0.75, 0.78))
			ramp.set_color(0, Color(col, 0.0))
			ramp.set_color(1, Color(col, 0.0))
			ramp.add_point(0.15, Color(col, 0.45 if steam else 0.35))
			ramp.add_point(0.6, Color(col, 0.2))
		"dust", "fireflies":
			var flies: bool = kind == "fireflies"
			p.amount = int(spec.get("amount", 14 if flies else 40))
			p.lifetime = 4.0 if flies else 7.0
			p.direction = Vector2(0.3, -1.0)
			p.spread = 180.0
			p.gravity = Vector2.ZERO
			p.initial_velocity_min = 0.002 * world.x
			p.initial_velocity_max = (0.012 if flies else 0.005) * world.x
			p.scale_amount_min = (size if size > 0.0 else (0.022 if flies else 0.005)) * world.x / 128.0
			p.scale_amount_max = p.scale_amount_min * 1.5
			var col2 := Color(c[0], c[1], c[2]) if c.size() >= 3 else (Color(0.95, 1.0, 0.55) if flies else Color(1.0, 0.95, 0.8))
			ramp.set_color(0, Color(col2, 0.0))
			ramp.set_color(1, Color(col2, 0.0))
			if flies:                                    # each one lights up twice in its life
				ramp.add_point(0.2, Color(col2, 0.95))
				ramp.add_point(0.4, Color(col2, 0.1))
				ramp.add_point(0.65, Color(col2, 0.9))
			else:
				ramp.add_point(0.3, Color(col2, 0.55))
				ramp.add_point(0.7, Color(col2, 0.55))
			if flies:
				var mat := CanvasItemMaterial.new()
				mat.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
				p.material = mat
		"rain", "snow", "leaves":
			var r2 := _rect(spec) if spec.has("rect") else Rect2(0.0, -0.05 * world.y, world.x, 0.02 * world.y)
			p.position = r2.get_center()
			p.emission_shape = CPUParticles2D.EMISSION_SHAPE_RECTANGLE
			p.emission_rect_extents = r2.size * 0.5
			p.amount = int(spec.get("amount", {"rain": 160, "snow": 90, "leaves": 16}[kind]))
			p.lifetime = {"rain": 1.1, "snow": 7.0, "leaves": 6.0}[kind]
			p.direction = Vector2(0.15, 1.0) if kind == "rain" else Vector2(0.2, 1.0)
			p.spread = 4.0 if kind == "rain" else 25.0
			p.gravity = Vector2(0.0, 0.25 * world.y) if kind == "rain" else Vector2(0.004 * world.x, 0.01 * world.y)
			p.initial_velocity_min = (1.0 if kind == "rain" else 0.04) * world.y * (0.9 if kind == "rain" else 1.0)
			p.initial_velocity_max = p.initial_velocity_min * 1.2
			p.scale_amount_min = (size if size > 0.0 else {"rain": 0.004, "snow": 0.008, "leaves": 0.02}[kind]) * world.x / 128.0
			p.scale_amount_max = p.scale_amount_min * 1.6
			if kind == "rain":                           # a streak along the way it falls
				p.texture = _streak_texture()
				p.particle_flag_align_y = true
				p.scale_amount_min = 0.035 * world.x / 96.0
				p.scale_amount_max = 0.05 * world.x / 96.0
			if kind == "leaves":
				p.texture = _leaf_texture()
				p.scale_amount_min = (size if size > 0.0 else 0.022) * world.x / 48.0
				p.scale_amount_max = p.scale_amount_min * 1.5
				p.angle_min = 0.0
				p.angle_max = 360.0
				p.angular_velocity_min = -120.0
				p.angular_velocity_max = 120.0
				p.hue_variation_min = -0.04
				p.hue_variation_max = 0.04
			var col3: Color = Color(c[0], c[1], c[2]) if c.size() >= 3 else {"rain": Color(0.75, 0.82, 0.95), "snow": Color(1, 1, 1),
					"leaves": Color(0.85, 0.5, 0.18)}[kind]
			var a0: float = {"rain": 0.45, "snow": 0.9, "leaves": 1.0}[kind]
			ramp.set_color(0, Color(col3, 0.0))
			ramp.set_color(1, Color(col3, 0.0))
			ramp.add_point(0.06, Color(col3, a0))
			ramp.add_point(0.9, Color(col3, a0))
		"sparks":
			p.amount = int(spec.get("amount", 20))
			p.lifetime = 1.2
			p.direction = Vector2(0.0, -1.0)
			p.spread = 25.0
			p.gravity = Vector2(0.0, 0.05 * world.y)
			p.initial_velocity_min = 0.05 * world.x
			p.initial_velocity_max = 0.11 * world.x
			p.scale_amount_min = (size if size > 0.0 else 0.005) * world.x / 128.0
			p.scale_amount_max = p.scale_amount_min * 1.6
			var col4 := Color(c[0], c[1], c[2]) if c.size() >= 3 else Color(1.0, 0.65, 0.2)
			ramp.set_color(0, Color(col4, 1.0))
			ramp.set_color(1, Color(col4, 0.0))
			var mat2 := CanvasItemMaterial.new()
			mat2.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
			p.material = mat2
		_:
			warnings.append("life: no particles of type '%s'" % kind)
	p.color_ramp = ramp
	p.preprocess = p.lifetime                 # (already going at the first frame)
	p.emitting = true
	return p
