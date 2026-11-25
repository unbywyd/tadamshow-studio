extends RefCounted
## Two-bone inverse kinematics, analytic. Pure functions, no state.
##
##     root o
##          |\             l1, l2  bone lengths
##       l1 | \ d          d       distance root -> target
##          |  \           bend    angle between the direction of bone 1 and of bone 2:
##      mid o---o target           0 = straight limb, the sign = which way the middle joint folds
##            l2

const EPS := 0.001

## `target` is relative to the root joint. `side` in -1..+1 picks the way the middle joint folds;
## a fraction makes the limb straighter than needed (used to swing the joint over to the other side).
## `bend_min` / `bend_max` are the middle joint's limits written as a bend angle.
## Returns Vector2(direction of bone 1, bend) in radians, in the frame `target` is given in.
static func solve(target: Vector2, l1: float, l2: float, side: float,
		bend_min: float, bend_max: float) -> Vector2:
	# Too far or too close: clamp the distance, so the limb simply points straight at the target.
	var d: float = clampf(target.length(), absf(l1 - l2) + EPS, l1 + l2)
	# Law of cosines in the triangle (l1, l2, d): the inner angle at the middle joint.
	var inner: float = acos(clampf((l1 * l1 + l2 * l2 - d * d) / (2.0 * l1 * l2), -1.0, 1.0))
	var bend: float = clampf(side * (PI - inner), bend_min, bend_max)
	# Angle between bone 1 and the line root -> end for this bend. Computed from the bend itself,
	# so it stays right when a limit has clamped the bend (the limb then aims at the target).
	var lead: float = atan2(l2 * sin(bend), l1 + l2 * cos(bend))
	return Vector2(target.angle() - lead, bend)


## An ARM's side. Not one line through the shoulder but a WEDGE: the elbow hangs under the hand for every way the
## arm points from the pole (out and steeply down) round by "out" and "up" to far inside above the head (WEDGE
## radians past the pole's opposite... see below); only an arm that points down, or down across the body, has its
## elbow on the other, outer side. With one line its far half comes up beside the head, and two hands at the ears
## get their elbows inside: the arms cross.
##   m = the angle from the pole to the arm, mirrored so that it reads the same for both arms:
##   m < 0 (towards "out", "up") or m > WEDGE (over the top, far inside): hanging;  0 < m < WEDGE: the outer side.
const WEDGE := 2.23           # radians (128 degrees): from the pole, past "down" and "in", to 15 degrees above "in"
static func side_wedge(target: Vector2, pole: Vector2, current: float, pole_sign: float, dead_zone: float = 0.12) -> float:
	var m: float = pole.angle_to(target) * pole_sign
	if minf(absf(m), absf(m - WEDGE)) < dead_zone:
		return current
	return (-1.0 if (m < 0.0 or m > WEDGE) else 1.0) * pole_sign


## The `side` that puts the middle joint on the `pole` side of the line root -> target.
## Near the line itself (|sin| < dead_zone) the current choice is kept, so it cannot flicker.
static func side_toward(target: Vector2, pole: Vector2, current: float, dead_zone: float = 0.15) -> float:
	var s: float = target.normalized().cross(pole.normalized())   # sine of the angle target -> pole
	if absf(s) < dead_zone:
		return current
	return -signf(s)
