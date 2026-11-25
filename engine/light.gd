extends RefCounted
## LIGHT AND SHADOW of a scene (docs/framework-tz.md 6.5). scene.json:
##   "grade": "day" | "evening" | "night" | "alarm" | {"tint": [r, g, b], "gain": 1, "sat": 1, "contrast": 1}
##            the colour of the whole picture; a script line {"grade": "night", "time": 2.0} goes over to another
##            one in that many seconds ("alarm" pulses red)
##   "vignette": 0.35         the corners darker
##   "light": {"at": [x, y]}  where the light comes from (shares of the world: a lamp, the moon, the sun low over
##            the edge); heroes cast a SHADOW of their own shape on the ground away from it and get a light RIM on
##            the side facing it. "shadow": 0.3 (how dark), "length": 0.45 (how long the shadow is against the
##            hero's height), "rim": 0.35 (how bright the rim), "color": [r, g, b] (of the rim)
## Without "light" a hero has only the soft spot under its feet (stage.gd _draw_shadow), as before.

const PRESETS := {
	"day": {"tint": [1.0, 1.0, 1.0], "gain": 1.0, "sat": 1.0, "contrast": 1.0},
	"evening": {"tint": [1.08, 0.95, 0.8], "gain": 0.9, "sat": 0.88, "contrast": 1.05},
	"night": {"tint": [0.74, 0.86, 1.15], "gain": 0.74, "sat": 0.62, "contrast": 1.08},
	"alarm": {"tint": [1.25, 0.78, 0.74], "gain": 0.92, "sat": 0.8, "contrast": 1.12, "pulse": 1.0},
}

var rect: ColorRect
var _from := {}
var _to := {}
var _t := 1.0
var _time := 0.0

static var _grade_shader: Shader
static var _rim_shader: Shader


## The grade layer over everything (not moved by the camera). `size`: the viewport.
func setup_grade(host: Node, spec: Dictionary, size: Vector2) -> void:
	if not spec.has("grade") and not spec.has("vignette"):
		return
	var layer := CanvasLayer.new()
	layer.layer = 50
	host.add_child(layer)
	rect = ColorRect.new()
	rect.size = size
	# (the whole window, whatever size it is now or becomes: a window made smaller than asked at the start - a tall
	# picture on a short screen - or stretched later left the grade over a part of the picture only)
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = _grade()
	rect.material = m
	layer.add_child(rect)
	m.set_shader_parameter("vignette", float(spec.get("vignette", 0.0)))
	_to = _resolve(spec.get("grade", "day"))
	_from = _to
	_apply(_to, 0.0)


## A script line {"grade": ..., "time": seconds}.
func change(grade: Variant, time: float) -> void:
	if rect == null:
		return
	_from = _current()
	_to = _resolve(grade)
	_t = 0.0
	_time = maxf(time, 0.0)


func step(n: int) -> void:
	if rect == null:
		return
	if _t < 1.0:
		_t = 1.0 if _time <= 0.0 else minf(_t + 1.0 / 60.0 / _time, 1.0)
	_apply(_current(), n / 60.0)


func _current() -> Dictionary:
	var u: float = smoothstep(0.0, 1.0, _t)
	var out := {}
	for k: String in ["gain", "sat", "contrast", "pulse"]:
		out[k] = lerpf(float(_from.get(k, 0.0 if k == "pulse" else 1.0)), float(_to.get(k, 0.0 if k == "pulse" else 1.0)), u)
	var a: Array = _from["tint"]
	var b: Array = _to["tint"]
	out["tint"] = [lerpf(a[0], b[0], u), lerpf(a[1], b[1], u), lerpf(a[2], b[2], u)]
	return out


func _apply(g: Dictionary, t: float) -> void:
	var m: ShaderMaterial = rect.material
	var tint: Array = g["tint"]
	# an alarm breathes: the red comes and goes once a second and a half
	var p: float = float(g.get("pulse", 0.0)) * (0.5 + 0.5 * sin(t * TAU / 1.5))
	m.set_shader_parameter("tint", Vector3(tint[0], lerpf(tint[1], tint[1] * 0.85, p), lerpf(tint[2], tint[2] * 0.85, p)))
	m.set_shader_parameter("gain", float(g["gain"]))
	m.set_shader_parameter("sat", float(g["sat"]))
	m.set_shader_parameter("contrast", float(g["contrast"]))


static func _resolve(g: Variant) -> Dictionary:
	if g is Dictionary:
		var d: Dictionary = PRESETS["day"].duplicate()
		d.merge(g, true)
		return d
	return PRESETS.get(str(g), PRESETS["day"]).duplicate()


static func _grade() -> Shader:
	if _grade_shader == null:
		_grade_shader = Shader.new()
		_grade_shader.code = """
shader_type canvas_item;
uniform sampler2D screen_tex : hint_screen_texture, filter_linear;
uniform vec3 tint = vec3(1.0);
uniform float gain = 1.0;
uniform float sat = 1.0;
uniform float contrast = 1.0;
uniform float vignette = 0.0;
void fragment() {
	vec3 c = texture(screen_tex, SCREEN_UV).rgb;
	float l = dot(c, vec3(0.299, 0.587, 0.114));
	c = mix(vec3(l), c, sat);
	c = (c - 0.5) * contrast + 0.5;
	c *= tint * gain;
	vec2 d = (SCREEN_UV - 0.5) * vec2(1.0, 1.25);
	c *= 1.0 - vignette * smoothstep(0.3, 0.85, length(d) * 1.3);
	COLOR = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""
	return _grade_shader


## The rim: a part's edge that faces the light is lit. One material for every part of a hero; the light's
## direction is given in the world and turned into each part's own frame in the vertex shader.
static func rim_material(dir: Vector2, strength: float, color: Color) -> ShaderMaterial:
	if _rim_shader == null:
		_rim_shader = Shader.new()
		_rim_shader.code = """
shader_type canvas_item;
uniform vec2 light_dir = vec2(-1.0, -0.5);    // towards the light, world
uniform float strength = 0.35;
uniform vec3 rim_color = vec3(1.0, 0.95, 0.8);
uniform float width = 3.0;                     // px of the picture the rim reaches in
varying vec2 local_dir;
void vertex() {
	// the light's direction in this part's own picture (a turned or mirrored part)
	mat2 m = mat2(MODEL_MATRIX[0].xy, MODEL_MATRIX[1].xy);
	local_dir = normalize(inverse(m) * light_dir);
}
void fragment() {
	vec4 c = COLOR;                                // (the picture, already times the part's modulate)
	vec2 px = TEXTURE_PIXEL_SIZE * width;
	// how much of the picture is missing a few px towards the light: there the edge faces it
	float out1 = 1.0 - texture(TEXTURE, UV + local_dir * px).a;
	float out2 = 1.0 - texture(TEXTURE, UV + local_dir * px * 2.0).a;
	float rim = clamp(max(out1, out2 * 0.6), 0.0, 1.0) * c.a;
	c.rgb = mix(c.rgb, max(c.rgb, rim_color), rim * strength);
	COLOR = c;
}
"""
	var m := ShaderMaterial.new()
	m.shader = _rim_shader
	m.set_shader_parameter("light_dir", dir.normalized())
	m.set_shader_parameter("strength", strength)
	m.set_shader_parameter("rim_color", Vector3(color.r, color.g, color.b))
	return m


## ---- The shadow of a hero's own shape, lying on the ground away from the light ----
## Every hero's shadow is a copy of every drawing of its puppet (the same pictures, the same places, each step),
## all black and OPAQUE, drawn into one picture the size of the world (a SubViewport). That picture is laid over the
## background at the shadows' strength: where two parts overlap it is no darker, and shadows lie on the ground
## under everyone. (A CanvasGroup per hero would do the same; in this build it drew nothing.)
var shadow_vp: SubViewport
var shadow_root: Node2D


func setup_shadows(host: Node, back: CanvasLayer, world_size: Vector2, alpha: float) -> void:
	shadow_vp = SubViewport.new()
	shadow_vp.size = Vector2i(world_size)
	shadow_vp.transparent_bg = true
	shadow_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	host.add_child(shadow_vp)
	shadow_root = Node2D.new()
	shadow_vp.add_child(shadow_root)
	var s := Sprite2D.new()
	s.centered = false
	s.texture = shadow_vp.get_texture()
	s.modulate = Color(1, 1, 1, alpha)
	back.add_child(s)


static func make_shadow(p: Node2D, root: Node2D) -> Dictionary:
	var group := Node2D.new()
	root.add_child(group)
	var copies: Array = []
	for part: Variant in p.parts.values():
		var s := Sprite2D.new()
		s.modulate = Color(0, 0, 0, 1)
		group.add_child(s)
		copies.append([part, s])
	var sk: Variant = p.parts.get("skirt")
	if sk != null:
		for c: Node in sk.node.get_children():
			if c is Polygon2D:
				var cloth := Polygon2D.new()
				cloth.color = Color(0, 0, 0, 1)
				group.add_child(cloth)
				copies.append([c, cloth])
	return {"group": group, "copies": copies, "puppet": p}


## `ground`: the transform from the hero's own layer to the world that lays the shape on the ground.
static func update_shadow(sh: Dictionary, ground: Transform2D, visible: bool) -> void:
	var group: Node2D = sh["group"]
	group.transform = ground
	group.visible = visible
	for pair: Array in sh["copies"]:
		var src: Variant = pair[0]
		if src is Polygon2D:
			var poly: Polygon2D = src
			var dst: Polygon2D = pair[1]
			dst.visible = poly.is_visible_in_tree()
			dst.texture = poly.texture
			dst.polygon = poly.polygon
			dst.uv = poly.uv
			dst.polygons = poly.polygons
			dst.transform = poly.get_global_transform()
			continue
		var spr: Sprite2D = src.sprite
		var s: Sprite2D = pair[1]
		# (a recorded head hides the painted one: its shape still casts the shadow)
		s.visible = spr.is_visible_in_tree() or (src.name == "head" and (src.node as Node2D).is_visible_in_tree())
		s.texture = spr.texture
		s.centered = spr.centered
		s.flip_h = spr.flip_h
		s.offset = spr.offset
		s.region_enabled = spr.region_enabled
		s.region_rect = spr.region_rect
		s.transform = spr.get_global_transform()


static func free_shadow(sh: Dictionary) -> void:
	if sh.has("group") and is_instance_valid(sh["group"]):
		(sh["group"] as Node).queue_free()


## The transform laying a hero's shape on the ground: squashed to `flat` of its height, slanted `lean` of its height
## sideways per height (away from the light, `dir` = -1 / 1), standing on the line y = `floor_y`.
static func ground_transform(floor_y: float, dir: float, lean: float, flat: float) -> Transform2D:
	return Transform2D(Vector2(1.0, 0.0), Vector2(-dir * lean, flat), Vector2(dir * lean * floor_y, floor_y * (1.0 - flat)))
