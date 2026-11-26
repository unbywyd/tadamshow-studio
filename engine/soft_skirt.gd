extends RefCounted
## A long skirt, a dress or a robe, drawn as a grid of triangles in place of its picture. Two ways, by the view:
##   - in PROFILE it is cloth: two edges hung from the waist (the painted outline of its picture, the front and the
##     back one), each kept on its own side of the legs, the picture drawn between them (_make_drape, _hang_edge);
##   - seen from the FRONT or the BACK it is a bell: the picture kept whole, only leaning, swinging and gathered at
##     the floor (_bell). A clean drawing matters more there than what real cloth would do.
## Both swing as one pendulum when the waist is jerked.
##
## What it was before, and why not: a chain of points the legs pushed about (in a jump the picture came apart in
## strips); a stack of plumb rows the legs widened like a tent (a row widened over a raised knee smeared its picture
## into streaks, and lying or sitting needed a threshold per pose); the picture tied to the leg bones as a grid (a
## wide skirt folded behind a bent knee, with a hole where a cell crossed itself); the two-edge cloth seen from the
## front as well (see _bell).
##
## Everything is in the puppet's own space (a mirrored puppet is mirrored with it). motion.gd steps it after the
## puppet. The skirt part's sprite is hidden; the mesh is drawn in its place, on its layer.

const LINKS := 10
const STRETCH := 2.2           # the widest a row of the picture is drawn, times its own width
const EDGE_SOFT := 6           # texture px kept outside the painted cloth's edge (its soft outline)
const SWAY_PULL := 60.0        # 1/s^2: how hard a front skirt is pulled back to plumb
const SWAY_DAMP := 7.0         # 1/s
const FRONT_SWING := 0.21     # radians (12 degrees): the most the hem swings off plumb

var puppet: Object
var part: Object
var mesh: Polygon2D
var side := false              # the hero is seen in profile
var floor_local := 1e9         # the floor, in puppet space
var top := 0.0                 # the picture's top edge, part frame (above the joint: the waistband)
var x0 := 0.0                  # the picture's left and right edges, part frame
var x1 := 0.0
var rows: PackedFloat32Array   # y of every chain point at rest, part frame (rows[0] = 0: the joint)
var pts: PackedVector2Array    # chain points now, puppet space
var size := Vector2.ONE
var sway := 0.0                # the one angle the skirt swings by (radians, at the hem)
var sway_v := 0.0
var _w1 := Vector2.ZERO        # the waist a step and two steps ago (its acceleration throws the hem)
var _w2 := Vector2.ZERO
var _w_known := 0
var squash := 1.0              # 1 = hangs its full length; less = pooled on the floor
var _diag := PackedByteArray()      # every grid cell: which way it is cut into two triangles now
const MIN_GAP := 0.15               # the least a row keeps below the row above it, in its spacing at rest
var _gc := 2                        # the grid drawn: its columns and rows
var _gr := 2
var jerk := 0.0                     # for the checks: the worst jump of a cloth point in one step, in skirt lengths
var _jerk_was := PackedVector2Array()    # the leg joints and the cloth's points, from the waist: a step ago
var _jerk_before := PackedVector2Array() # ...and two steps ago
var _jerk_known := 0
var drape := false                  # made: the cloth hung from the waist and laid over the legs (below)
const DRAPE_ROWS := 26
const TURN_STEP := 0.2             # radians: how finely a link stopped by a leg is turned to find its way out
const BELL_COLS := 13              # seen from the front or the back: points across a row
const BELL_LEAN := 0.45            # radians: the most the hem of a front skirt leans off the body's line, towards plumb
const BELL_WIDE := 1.3             # the widest a half of a row is drawn over a leg set aside, times its own width
const BELL_SHORT := 0.6            # the shortest it is gathered to at the floor (what is left goes below the floor line)
const BELL_MOST := 1.5             # ...and with the gathering at the floor on top of that
const LEG_GAP := 3.0                # px the cloth keeps off a leg
var _e_rest: Array = []             # [column 0, column 1]: the picture's painted edge down every row, at rest, puppet space
var _e_top := 0                     # rows up to this one are the waist: they go with the pelvis
var _e_inv := Transform2D.IDENTITY  # the pelvis at rest, inverted
var _front_col := 1                 # which column is the front edge (the way the hero faces)
var _front_sign := 1.0              # ...and the way that is, along x in puppet space
var _winding := 1.0                 # the sign of a grid cell's area at rest (a mirrored puppet turns it)


static func make(p: Object, skirt: Object, in_profile: bool) -> Variant:
	var s = load("res://soft_skirt.gd").new()
	s.puppet = p
	s.part = skirt
	s.side = in_profile
	var tex: Texture2D = skirt.sprite.texture
	s.size = tex.get_size()
	var pos: Vector2 = skirt.sprite.position          # top-left of the picture in the part's frame
	s.top = pos.y
	s.x0 = pos.x
	s.x1 = pos.x + s.size.x
	var bottom: float = pos.y + s.size.y
	s.rows = PackedFloat32Array()
	for i in LINKS + 1:
		s.rows.append(lerpf(0.0, bottom, float(i) / LINKS))
	s.mesh = Polygon2D.new()
	s.mesh.texture = tex
	s.mesh.z_index = skirt.sprite.z_index
	# (anisotropic: a skirt gathered at the floor is drawn much shorter but no narrower, and a plain mipmap, picked
	# by the shorter way, blurred it and broke its thin drawn lines into dashes)
	s.mesh.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	if not s._make_drape(pos):
		return null                                    # (no legs to hang it over: the skirt stays a stiff part)
	p.add_child(s.mesh)
	skirt.sprite.visible = false
	skirt.rigid = true            # its waist holds plumb; the cloth itself does the swinging
	s.reset()
	return s


## Every cell as two triangles, cut along the diagonal that leaves both the right way round (a cell bent into an
## arrowhead has one such). Triangles are always drawn; a four-cornered cell that crosses itself is not, at all.
func _cut(all: bool) -> void:
	var poly: PackedVector2Array = mesh.polygon
	var changed := all
	for r in range(1, _gr):
		for c in range(1, _gc):
			var a: int = (r - 1) * _gc + (c - 1)
			var b: int = a + 1
			var d: int = a + _gc
			var e: int = d + 1
			# cut a-e: triangles a b e, a e d; cut b-d: a b d, b e d
			var ae: float = minf((poly[b] - poly[a]).cross(poly[e] - poly[a]), (poly[e] - poly[a]).cross(poly[d] - poly[a])) * _winding
			var bd: float = minf((poly[b] - poly[a]).cross(poly[d] - poly[a]), (poly[e] - poly[b]).cross(poly[d] - poly[b])) * _winding
			var k: int = (r - 1) * (_gc - 1) + (c - 1)
			var want: int = 1 if bd > ae and ae <= 0.0 else 0
			if _diag[k] != want:
				_diag[k] = want
				changed = true
	if not changed:
		return
	var polys: Array = []
	for r in range(1, _gr):
		for c in range(1, _gc):
			var a: int = (r - 1) * _gc + (c - 1)
			var b: int = a + 1
			var d: int = a + _gc
			var e: int = d + 1
			if _diag[(r - 1) * (_gc - 1) + (c - 1)] == 1:
				polys.append(PackedInt32Array([a, b, d]))
				polys.append(PackedInt32Array([b, e, d]))
			else:
				polys.append(PackedInt32Array([a, b, e]))
				polys.append(PackedInt32Array([a, e, d]))
	mesh.polygons = polys


## ---- In PROFILE: the cloth DRAPED ----
## The skirt has two edges, the front one and the back one (the painted outline of its picture, row by row). Each
## hangs from the waist the way it is drawn, link after link, and gives way to what is under it:
##   - a leg: the front edge stays in FRONT of every thigh and shin, the back edge BEHIND them. "In front" is the
##     bone's own front side, so it turns with the bone: on a thigh raised level it is the top (the cloth lies on
##     the lap, then falls from the knee), on a hero lying on its back it is the top too. An edge never gets to the
##     other side of a leg, so no leg comes out of the cloth, in any pose, and nothing is guessed about the pose.
##   - the floor: the cloth lies on it and goes on along it.
## The picture is then drawn row by row between the two edges.
## Rows are kept one under another and never turned
## over (_settle), and are drawn as triangles: a hole or a tear cannot be drawn at all.
## Nothing is remembered from frame to frame but one swing angle, so the cloth cannot get caught on the wrong side.
## (Before: the picture tied to the leg bones, as cut-out tools skin a mesh. A wide skirt turned with the thigh and
## then with the shin as two stiff plates; behind a bent knee they ran into each other: a fold, squashed flowers and,
## where a cell crossed itself, a hole. And a skirt standing still followed every bend of the knees.)
func _make_drape(pos: Vector2) -> bool:
	for n: String in ["pelvis", "thigh_l", "thigh_r", "shin_l", "shin_r"]:
		if not puppet.parts.has(n):
			return false
	var tex: Texture2D = mesh.texture
	var img: Image = tex.get_image()
	if img != null and img.is_compressed():
		img.decompress()
	_e_inv = (puppet.parts["pelvis"].xf as Transform2D).affine_inverse()
	var foot: Object = puppet.parts.get("foot_l")
	# (seen from the front or the back the two edges are the left and the right one, and only their rest shape is
	# used: see _bell)
	_front_sign = -1.0 if side and foot != null and (foot.xf as Transform2D).basis_xform(foot.center).x < -1.0 else 1.0
	_front_col = 1 if _front_sign > 0.0 else 0
	var hip_y: float = 0.5 * (puppet.parts["thigh_l"].xf.origin.y + puppet.parts["thigh_r"].xf.origin.y)
	var uv := PackedVector2Array()
	var cols: int = 2 if side else BELL_COLS
	_e_rest = [PackedVector2Array(), PackedVector2Array()]
	_e_top = 0
	var step_v: float = size.y / float(DRAPE_ROWS - 1)
	# the painted edge over the whole band every row stands for (an edge taken on one line cuts off what sticks
	# out between two rows: a frill, an apron's corner); a row with no paint at all (the picture's empty top or
	# bottom margin) is as wide as the nearest painted one
	var spans: Array = []
	for r in DRAPE_ROWS:
		spans.append(_band_span(img, step_v * r - 0.5 * step_v, step_v * r + 0.5 * step_v))
	for r in DRAPE_ROWS:
		var near := 1
		while (spans[r] as Vector2).y < 0.0 and near < DRAPE_ROWS:
			for o: int in [r + near, r - near]:
				if o >= 0 and o < DRAPE_ROWS and (spans[o] as Vector2).y >= 0.0:
					spans[r] = spans[o]
					break
			near += 1
		if (spans[r] as Vector2).y < 0.0:
			spans[r] = Vector2(0.0, size.x)
	# The edge the cloth is hung by is the outline's smooth OUTSIDE: a ragged hem or a frill goes in and out from
	# row to row, and an edge that does so comes out as saw teeth once it lies along a leg. The rags themselves are
	# in the picture, inside this edge.
	for turn in 2:
		var smooth: Array = []
		for r in DRAPE_ROWS:
			var a: Vector2 = spans[maxi(r - 1, 0)]
			var b: Vector2 = spans[r]
			var c: Vector2 = spans[mini(r + 1, DRAPE_ROWS - 1)]
			smooth.append(Vector2(minf(b.x, 0.25 * a.x + 0.5 * b.x + 0.25 * c.x), maxf(b.y, 0.25 * a.y + 0.5 * b.y + 0.25 * c.y)))
		spans = smooth
	# ...and it never turns sharply inwards on its way down (a hem rounded off at its corners, a rag cut away): a
	# link of the edge pointing into the leg is thrown out forwards by it, a link's length at once
	for r in range(1, DRAPE_ROWS):
		var up: Vector2 = spans[r - 1]
		var it: Vector2 = spans[r]
		spans[r] = Vector2(minf(it.x, up.x + 0.35 * step_v), maxf(it.y, up.y - 0.35 * step_v))
	for r in DRAPE_ROWS:
		var v: float = step_v * r
		var lo: float = (spans[r] as Vector2).x
		var hi: float = (spans[r] as Vector2).y
		for c in cols:
			uv.append(Vector2(lerpf(lo, hi, float(c) / float(cols - 1)), v))
		_e_rest[0].append(part.xf * (pos + Vector2(lo, v)))
		_e_rest[1].append(part.xf * (pos + Vector2(hi, v)))
		if _e_rest[0][r].y <= hip_y:
			_e_top = r
	_gc = cols
	_gr = DRAPE_ROWS
	var a0: float = (_e_rest[1][0] - _e_rest[0][0]).cross(_e_rest[0][1] - _e_rest[0][0])
	_winding = signf(a0) if a0 != 0.0 else 1.0
	mesh.uv = uv
	mesh.polygon = uv
	_diag = PackedByteArray()
	_diag.resize((DRAPE_ROWS - 1) * (cols - 1))
	_cut(true)
	drape = true
	return true


## The first and last painted pixel over the picture's rows v0..v1 (a few px of its soft edge kept outside);
## y < 0 if nothing is painted there.
static func _band_span(img: Image, v0: float, v1: float) -> Vector2:
	if img == null:
		return Vector2(0.0, 1e9)
	var w: int = img.get_width()
	var h: int = img.get_height()
	var lo: int = w
	var hi: int = -1
	var y: int = maxi(int(v0), 0)
	while y <= mini(int(v1), h - 1):
		for x in w:
			if img.get_pixel(x, y).a > 0.5:
				lo = mini(lo, x)
				break
		for x in range(w - 1, -1, -1):
			if img.get_pixel(x, y).a > 0.5:
				hi = maxi(hi, x + 1)
				break
		y += 2
	if hi < 0:
		return Vector2(0.0, -1.0)
	return Vector2(float(maxi(lo - EDGE_SOFT, 0)), float(mini(hi + EDGE_SOFT, w)))


## The thighs and shins as the cloth meets them: [start, direction, length, half thickness, front side, is a thigh].
func _bones() -> Array:
	var out: Array = []
	for n: String in ["thigh_l", "thigh_r", "shin_l", "shin_r"]:
		var p: Object = puppet.parts[n]
		var a: Vector2 = p.xf.origin
		var b: Vector2
		if n.begins_with("thigh"):
			b = puppet.parts["shin" + n.substr(5)].xf.origin
		else:
			var foot: Object = puppet.parts.get("foot" + n.substr(4))
			b = foot.xf.origin if foot != null else p.xf * (p.center * 2.0)
		var d: Vector2 = b - a
		var l: float = d.length()
		if l < 1.0:
			continue
		d /= l
		out.append([a, d, l, 0.5 * minf(p.painted.size.x, p.painted.size.y) + LEG_GAP, Vector2(d.y, -d.x) * _front_sign, n.begins_with("thigh")])
	return out


## Where an edge STARTS (the waistband's end), put out of every leg it is in, on its own side of it (side +1: the
## front edge comes out in front, -1: the back one behind). The front one is kept in front of a THIGH all along it,
## however far behind it is: when a thigh comes up past the belly (a deep crouch), the cloth still starts over the
## thigh. Nothing else is: a leg's "front" is a whole half of the picture (held to it, the back of the waistband
## jumped over a raised thigh, and the front of it under a shin folded back in a crouch).
func _start(q: Vector2, side: float, bones: Array) -> Vector2:
	for b: Array in bones:
		var rel: Vector2 = q - b[0]
		var t: float = rel.dot(b[1])
		var r: float = b[3]
		if t < -r or t > b[2] + r:
			continue
		var over: float = maxf(maxf(-t, t - b[2]), 0.0)                  # past the bone's end: its round tip
		var need: float = sqrt(maxf(r * r - over * over, 0.0))
		var nrm: Vector2 = b[4] * side
		var l: float = rel.dot(nrm)
		if l < need and (l > -need or (side > 0.0 and bool(b[5]) and over == 0.0)):
			q += nrm * (need - l)
	return q


## How far (radians) the link `base` from `prev` must be turned, the way `way` (+1 or -1), for its end to come out of
## the legs; -1 if it never does.
func _turn_out(prev: Vector2, base: Vector2, way: float, bones: Array) -> float:
	var held := 0.0
	var a := TURN_STEP
	while a <= PI:
		if _in_leg(prev + base.rotated(way * a), bones) < 0:
			for it in 5:
				var mid: float = 0.5 * (held + a)
				if _in_leg(prev + base.rotated(way * mid), bones) < 0:
					a = mid
				else:
					held = mid
			return a
		held = a
		a += TURN_STEP
	return -1.0


## Which leg the point is in (the one it is deepest in), -1: none.
func _in_leg(q: Vector2, bones: Array) -> int:
	if q.y >= floor_local - 2.0:
		return -1                 # (on the floor or under it: the floor has it; a leg lying there is ON the cloth)
	var best := -1
	var deep := 0.5
	for i in bones.size():
		var b: Array = bones[i]
		var rel: Vector2 = q - b[0]
		var t: float = rel.dot(b[1])
		var r: float = b[3]
		if t < -r or t > b[2] + r:
			continue
		var over: float = maxf(maxf(-t, t - b[2]), 0.0)
		var in_by: float = sqrt(maxf(r * r - over * over, 0.0)) - absf(rel.dot(b[4]))
		if in_by > deep:
			deep = in_by
			best = i
	return best


## Cloth that would be under the floor lies on it, and goes on along it as far as it would have gone under: towards
## `under_x` if that is given (the back edge runs under the front one), else `way` (-1..1) of that length. Smoothly:
## a hem that only just touches the floor is only just moved (kept at its full length there, it had two places to be,
## in front and behind, and jumped between them at every step of a walk).
func _on_floor(q: Vector2, way: float, under_x: float) -> Vector2:
	var under: float = q.y - (floor_local - 1.0)
	if under <= 0.0:
		return q
	if is_finite(under_x):
		return Vector2(q.x + clampf(under_x - q.x, -under, under), floor_local - 1.0)
	return Vector2(q.x + under * way, floor_local - 1.0)


## One edge hung from the waist, link after link. A link hangs the way it is drawn (swung by `swing` at the hem). If
## that puts its end inside a leg, it is turned away from the leg just as far as it takes to bring the end out: so it
## lies ON the leg's surface. That is all the rule there is, and it needs no "lies" or "hangs" to be decided: on a
## raised thigh the links lie along it to the knee, go round the knee, and where the surface turns down as steeply
## as the cloth hangs they come off it by themselves. A link that only grazes a leg is only just turned, so nothing
## jumps as a pose changes. And a link is shorter than a leg is thick, so an edge that starts on its own side of a
## leg cannot come out on the other.
## (Tried before: the link pushed out and slid, with a threshold for "it lies"; at the knee it switched from frame
## to frame and all the cloth below it jumped a link's length. And left to gravity alone, the cloth slid down a
## raised thigh back to the hip, as a real skirt does on someone lying with the knees up, and bared the legs.)
## `partner`: the other edge, already hung (on the floor this one runs under it: the back of a skirt sat on is
## under the legs, not away behind).
func _hang_edge(col: int, side: float, bones: Array, at: Transform2D, swing: float, floor_way: float, partner: Variant) -> PackedVector2Array:
	var rest: PackedVector2Array = _e_rest[col]
	var n: int = rest.size()
	var out := PackedVector2Array()
	out.resize(n)
	# Which way a stopped link is turned: ALWAYS the same for an edge. Going from the waist to the hem, the front
	# edge has the legs on one hand and the back edge on the other, in every pose (that is what "in front of the
	# legs" means), so turning away from a leg is turning one way. (Worked out link by link from the surface it
	# hit, the way flipped where the link ran nearly along that surface: at the knee of a deep crouch the hem
	# jumped to the floor and back, and round a knee the links went backwards over the lap.)
	var way: float = -_front_sign * side
	for k in n:
		var under_x: float = (partner as PackedVector2Array)[k].x if partner != null else INF
		if k == 0:
			out[k] = _on_floor(_start(at * rest[k], side, bones), floor_way, under_x)
			continue
		# down to the hips the cloth is on the body and turns with the pelvis; below them it hangs. Both are links
		# of one edge, and a leg turns both aside alike: with the waist held stiff, a thigh raised to the belly (a
		# deep crouch) went THROUGH it, the top of the edge on one side of the leg and the rest on the other
		var base: Vector2
		if k <= _e_top:
			base = at.basis_xform(rest[k] - rest[k - 1])
		else:
			base = rest[k] - rest[k - 1]
			# gathered at the floor: shorter, and wider for it
			base = Vector2(base.x * (1.0 + 0.7 * (1.0 - squash)) + side * _front_sign * 0.35 * (1.0 - squash) * absf(base.y), base.y * squash)
			base = base.rotated(swing * float(k - _e_top) / float(n - 1 - _e_top))
		var prev: Vector2 = out[k - 1]
		var q: Vector2 = prev + base
		var hit: int = _in_leg(q, bones)
		if hit >= 0:
			var angle: float = _turn_out(prev, base, way, bones)
			if angle >= 0.0:
				q = prev + base.rotated(way * angle)
			else:
				q = _start(q, side, bones)                               # (walled in on every side: just out of it)
		out[k] = _on_floor(q, floor_way, under_x)
	return out


## ---- Seen from the FRONT or the BACK: a bell ----
## The picture as it is drawn, kept whole: it is never laid along a leg, pulled to a foot or folded on the floor. All
## that happens to it:
##   - down to the hips it is on the body; below them it goes on along the body's own line, bent a little towards
##     plumb (a body leaning aside: the skirt hangs; a body lying down: the skirt lies with it, as a paper doll's
##     does) and by the swing;
##   - on an upright body near the floor it is gathered: shorter and wider (squash);
##   - a half of a row is drawn wider over a leg set aside, BELL_WIDE at most. A leg further out than that shows from
##     under the skirt, and a skirt longer than the way to the floor of a hero sitting on it is drawn below the
##     floor line: both look like a puppet, neither spoils the picture.
## (Before, the two-edge cloth of the profile was used here too. Its edges lay along legs set wide apart, to the
## feet: the picture between them was pulled into a thin sheet, pleats came out as waves and streaks, a tail of it
## ran along the floor. Every pose was "covered" and none of them was clean.)
func _bell(at: Transform2D, swing: float, bones: Array) -> PackedVector2Array:
	var left: PackedVector2Array = _e_rest[0]
	var right: PackedVector2Array = _e_rest[1]
	var n: int = left.size()
	var step: float = size.y / float(n - 1)                 # the spacing of the rows at rest
	# how far the body's own "down" is off plumb, and how much of that the hem gives back
	var down: Vector2 = at.basis_xform(Vector2(0.0, 1.0)).normalized()
	var off: float = down.angle_to(Vector2(0.0, 1.0))
	var lean: float = BELL_LEAN * tanh(off / BELL_LEAN) * (1.0 - smoothstep(0.6, 1.4, absf(off)))
	var bend: float = lean + swing
	var mid := PackedVector2Array()             # the middle of every row...
	var turn := PackedFloat32Array()            # ...and how far the row is turned off the body's line
	mid.resize(n)
	turn.resize(n)
	for k in n:
		var c: Vector2 = (left[k] + right[k]) * 0.5
		if k <= _e_top:
			mid[k] = at * c
			turn[k] = 0.0
			continue
		var t: float = float(k - _e_top) / float(n - 1 - _e_top)
		var seg: Vector2 = c - (left[k - 1] + right[k - 1]) * 0.5
		turn[k] = bend * t
		mid[k] = mid[k - 1] + at.basis_xform(Vector2(seg.x, seg.y * squash)).rotated(turn[k])
	# wider over the legs: every point of a leg asks the row it is by for room, on its own side
	var wide_l := PackedFloat32Array()
	var wide_r := PackedFloat32Array()
	wide_l.resize(n)
	wide_r.resize(n)
	wide_l.fill(1.0)
	wide_r.fill(1.0)
	var across: Vector2 = at.basis_xform(Vector2(1.0, 0.0)).normalized()
	for b: Array in bones:
		for i in 5:
			var q: Vector2 = (b[0] as Vector2) + (b[1] as Vector2) * (float(b[2]) * i / 4.0)
			var best := -1
			var near := INF
			for k in range(_e_top + 1, n):
				var along: float = absf((q - mid[k]).dot(across.rotated(turn[k]).orthogonal()))
				if along < near:
					near = along
					best = k
			if best < 0 or near > 2.0 * step:
				continue                                  # (past the hem, or above the hips: no row is by it)
			var s: float = (q - mid[best]).dot(across.rotated(turn[best]))
			var half: float = maxf(0.5 * left[best].distance_to(right[best]), 1.0)
			var want: float = minf((absf(s) + float(b[3])) / half, BELL_WIDE)
			if s < 0.0:
				wide_l[best] = maxf(wide_l[best], want)
			else:
				wide_r[best] = maxf(wide_r[best], want)
	# ...and the rows next to it follow, a little less each (the bell stays smooth); nothing at the hips themselves
	for w: PackedFloat32Array in [wide_l, wide_r]:
		for k in range(_e_top + 2, n):
			w[k] = maxf(w[k], w[k - 1] - 0.03)
		for k in range(n - 2, _e_top, -1):
			w[k] = maxf(w[k], w[k + 1] - 0.03)
		for k in range(_e_top + 1, n):
			w[k] = minf(w[k], 1.0 + 0.08 * float(k - _e_top))
	var poly := PackedVector2Array()
	poly.resize(_gc * n)
	for k in n:
		var c: Vector2 = (left[k] + right[k]) * 0.5
		var t: float = maxf(float(k - _e_top) / float(n - 1 - _e_top), 0.0)
		var flare: float = 1.0 + 0.7 * (1.0 - squash) * t
		for col in _gc:
			var u: float = float(col) / float(_gc - 1)
			var from_mid: Vector2 = left[k].lerp(right[k], u) - c
			var w: float = minf(flare * (wide_l[k] if u < 0.5 else wide_r[k]), BELL_MOST)
			poly[_gc * k + col] = mid[k] + at.basis_xform(from_mid * w).rotated(turn[k])
	return poly


## The skirt now.
func _step_drape(dt: float) -> void:
	var pelvis: Transform2D = puppet.parts["pelvis"].xf
	var at: Transform2D = pelvis * _e_inv
	var waist: Vector2 = part.xf.origin
	var upright: float = smoothstep(0.82, 0.97, pelvis.basis_xform(Vector2(0.0, 1.0)).normalized().y)
	if dt > 0.0:
		var acc: float = clampf((waist.x - 2.0 * _w1.x + _w2.x) / (dt * dt), -40000.0, 40000.0) if _w_known >= 2 else 0.0
		_w2 = _w1
		_w1 = waist
		_w_known = mini(_w_known + 1, 2)
		sway_v += (-SWAY_PULL * sway - SWAY_DAMP * sway_v - acc / maxf(size.y, 1.0) * upright) * dt
		sway += sway_v * dt
		if absf(sway) > FRONT_SWING:
			sway = signf(sway) * FRONT_SWING
			sway_v = 0.0
	var bones: Array = _bones()
	var swing: float = -sway * upright
	var hips: float = 0.5 * ((at * (_e_rest[0][_e_top] as Vector2)).y + (at * (_e_rest[1][_e_top] as Vector2)).y)
	var full: float = maxf((_e_rest[0][DRAPE_ROWS - 1] as Vector2).y - (_e_rest[0][_e_top] as Vector2).y, 1.0)
	var poly := PackedVector2Array()
	if side:
		# cloth lying on the floor goes on the way the legs point along it
		var legs_way := 0.0
		for b: Array in bones:
			legs_way += (b[1] as Vector2).x
		var lead_way: float = clampf(legs_way / 2.0, -1.0, 1.0)
		var back_col: int = 1 - _front_col
		# A skirt that hangs and is longer than the way to the floor (the body squatting) is gathered: all of it gets
		# shorter and wider, and its hem stays in sight (cut off by the floor, a long dress sank into it). Not when
		# the cloth lies along the legs (sitting on the floor, lying): then it goes on along the floor instead.
		var hangs: float = upright * (1.0 - absf(lead_way))
		squash = lerpf(1.0, clampf((floor_local - hips) / full, 0.45, 1.0), hangs)
		var front: PackedVector2Array = _hang_edge(_front_col, 1.0, bones, at, swing, lead_way, null)
		var back: PackedVector2Array = _hang_edge(back_col, -1.0, bones, at, swing, lead_way, front)
		_settle(front, back)
		poly.resize(2 * DRAPE_ROWS)
		for k in DRAPE_ROWS:
			poly[2 * k + _front_col] = front[k]
			poly[2 * k + back_col] = back[k]
	else:
		squash = lerpf(1.0, clampf((floor_local - hips) / full, BELL_SHORT, 1.0), upright)
		poly = _bell(at, swing, bones)
	if dt > 0.0:
		# For the checks: the most a point of the cloth is thrown about in one step (a link flipping over, the hem
		# jumping from one place to another: seen as a flicker), beyond what the legs under it are thrown about
		# themselves in that step (a body hitting the floor, a pose set at once: the cloth must follow those).
		var now := PackedVector2Array()
		for b: Array in bones:
			now.append((b[0] as Vector2) - waist)
			now.append((b[0] as Vector2) + (b[1] as Vector2) * float(b[2]) - waist)
		for i in poly.size():
			now.append(poly[i] - waist)
		if _jerk_known >= 2 and _jerk_was.size() == now.size():
			var legs := 0.0
			var cloth_j := 0.0
			for i in now.size():
				var j: float = (now[i] - 2.0 * _jerk_was[i] + _jerk_before[i]).length()
				if i < 2 * bones.size():
					legs = maxf(legs, j)
				else:
					cloth_j = maxf(cloth_j, j)
			jerk = maxf(jerk, maxf(cloth_j - 1.5 * legs, 0.0) / maxf(size.y, 1.0))
		_jerk_before = _jerk_was if _jerk_known >= 1 and _jerk_was.size() == now.size() else now
		_jerk_was = now
		_jerk_known = mini(_jerk_known + 1, 2)
	mesh.polygon = poly
	_cut(false)
	for i in pts.size():
		var r: int = clampi(int(round(float(i) / LINKS * (DRAPE_ROWS - 1))), 0, DRAPE_ROWS - 1)
		pts[i] = (poly[_gc * r] + poly[_gc * r + _gc - 1]) * 0.5
		pts[i].y = minf(pts[i].y, floor_local)       # (a front skirt drawn under the floor line LIES on the floor)


## The rows put in order: none wider than the picture can be stretched (STRETCH), none narrower than a third of
## itself, each below the one before it (never turned over), nothing under the floor.
func _settle(front: PackedVector2Array, back: PackedVector2Array) -> void:
	var rest_f: PackedVector2Array = _e_rest[_front_col]
	var rest_b: PackedVector2Array = _e_rest[1 - _front_col]
	var axis := Vector2(_front_sign, 0.0)
	for k in front.size():
		var w0: float = maxf(rest_f[k].distance_to(rest_b[k]), 1.0)
		var d: Vector2 = front[k] - back[k]
		var w: float = d.length()
		if w > STRETCH * w0:
			var mid: Vector2 = (front[k] + back[k]) * 0.5
			front[k] = mid + d * (0.5 * STRETCH * w0 / w)
			back[k] = mid - d * (0.5 * STRETCH * w0 / w)
		if k > 0:
			var up: Vector2 = front[k - 1] - back[k - 1]
			if up.length_squared() > 1.0:
				axis = up.normalized()
			var down: Vector2 = Vector2(-axis.y, axis.x) * _front_sign
			var gap: float = MIN_GAP * rest_f[k].distance_to(rest_f[k - 1])
			var df: float = (front[k] - front[k - 1]).dot(down)
			if df < gap:
				front[k] += down * (gap - df)
			var db: float = (back[k] - back[k - 1]).dot(down)
			if db < gap:
				back[k] += down * (gap - db)
			var across: float = (front[k] - back[k]).dot(axis)
			if across < 0.3 * w0:
				front[k] += axis * (0.5 * (0.3 * w0 - across))
				back[k] -= axis * (0.5 * (0.3 * w0 - across))
		front[k].y = minf(front[k].y, floor_local - 1.0)
		back[k].y = minf(back[k].y, floor_local - 1.0)


## Hangs the chain straight from the skirt part as it is now.
func reset() -> void:
	pts = PackedVector2Array()
	for y in rows:
		pts.append(part.xf * Vector2(0.0, y))
	squash = 1.0
	sway = 0.0
	sway_v = 0.0
	_w_known = 0
	_jerk_known = 0
	_step_drape(0.0)


func step(dt: float, floor_y_world: float) -> void:
	floor_local = (puppet as Node2D).to_local(Vector2(0.0, floor_y_world)).y
	if mesh.texture != part.sprite.texture:
		mesh.texture = part.sprite.texture       # (the skirt's drawing is frames, frames.gd: the cloth shows the same one)
	_step_drape(dt)


## How well it does its job, for the checks (engine/tools/action_check.gd): x = how far a leg sticks out of the
## cloth ABOVE the hem (the worst, in leg thicknesses: the cloth should be over it), y = 1 if the rows are out of
## order (the picture would be torn or folded over itself).
func exposed() -> Vector2:
	# (seen from the front the skirt is a bell, and a leg set wide aside is MEANT to show from under it: "draped" is
	# not measured then at all. It was measured and thrown away, and it is the dear part: every step, a dozen points
	# of the thighs against every cell of the grid. A front hero in a skirt checked in minutes; now as fast as one
	# in trousers, with the same results.)
	return _exposed_grid(side)


## Draped (only when `draped`): the thighs' middle lines (hip to knee) must be inside the grid's outline; how far the
## worst point is outside, in thigh thicknesses. Torn: a grid cell turned inside out (its corners in the wrong order).
func _exposed_grid(draped := true) -> Vector2:
	var poly: PackedVector2Array = mesh.polygon
	# every cell of the grid as its own little polygon: a point is covered if it is inside any of them (the outline
	# of a folded grid crosses itself, and "inside the outline" then says nonsense)
	var cells: Array = []
	for r2 in (range(1, _gr) if draped else []):
		for c in range(1, _gc):
			var a2: int = (r2 - 1) * _gc + (c - 1)
			cells.append(PackedVector2Array([poly[a2], poly[a2 + 1], poly[a2 + 1 + _gc], poly[a2 + _gc]]))
	var worst := 0.0
	for sfx in (["_l", "_r"] if draped else []):
		var th: Object = puppet.parts["thigh" + sfx]
		var r: float = 0.5 * minf(th.painted.size.x, th.painted.size.y)
		var a: Vector2 = th.xf.origin
		var b: Vector2 = puppet.parts["shin" + sfx].xf.origin
		for k in range(2, 8):                       # (not the hip itself, at the waistband's edge, nor the knee's tip)
			var q: Vector2 = a.lerp(b, k / 8.0)
			if q.y >= floor_local - 2.0:
				continue
			var d := INF
			for cell: PackedVector2Array in cells:
				if Geometry2D.is_point_in_polygon(q, cell):
					d = 0.0
					break
				for j in 4:
					d = minf(d, Geometry2D.get_closest_point_to_segment(q, cell[j], cell[(j + 1) % 4]).distance_to(q))
			worst = maxf(worst, d / (2.0 * r))
	# torn: how much of the cloth's area is turned inside out. A knee bending folds the cloth on its inner side by a
	# few px (a crease, every cloth does it); a share of the whole is what shows (the smeared streaks were such)
	var flipped := 0.0
	var total := 0.0
	for r2 in range(1, _gr):
		for c in range(1, _gc):
			var a2: int = (r2 - 1) * _gc + (c - 1)
			var quad := PackedVector2Array([poly[a2], poly[a2 + 1], poly[a2 + 1 + _gc], poly[a2 + _gc]])
			var area := 0.0
			for k in 4:
				area += quad[k].cross(quad[(k + 1) % 4])
			area *= 0.5 * _winding
			total += absf(area)
			if area < 0.0:
				flipped -= area
	var torn: float = flipped / maxf(total, 1.0)
	return Vector2(worst, torn)


## The lowest point of the cloth, world.
func lowest_world() -> float:
	var low := -INF
	for q in pts:
		low = maxf(low, (puppet as Node2D).to_global(q).y)
	return low
