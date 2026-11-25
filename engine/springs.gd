extends RefCounted
## Fixed-step integrators for secondary motion. Our own maths instead of the physics engine,
## so the same input always gives the same motion.


## How one kind of joint behaves.
class Params:
	var stiffness: float   # 1/s^2  pull toward the goal angle; 0 = a free pendulum
	var damping: float     # 1/s    friction in the joint
	var gravity: float     # 0..1   how much gravity acts on the part
	var inertia: float     # 0..1   how strongly the parent's motion throws the part around

	func _init(k: float, c: float, g: float, i: float) -> void:
		stiffness = k
		damping = c
		gravity = g
		inertia = i


## One step for one joint angle. Returns Vector2(new angle, new velocity).
##
## The part is treated as a weight at distance `length` from its joint, in world direction `dir`.
## Only a push across the limb, along n = (-sin dir, cos dir), turns it:
##   gravity         + (g . n) / length          swings it toward hanging down
##   the joint moves - (joint_acc . n) / length  the weight lags behind its joint
##   the parent turns - parent_rot_acc           the part keeps its direction in the world
##   spring          + stiffness * (goal - angle)
##   friction        - damping * velocity
static func step(angle: float, vel: float, goal: float, p: Params, dir: float, length: float,
		joint_acc: Vector2, parent_rot_acc: float, gravity: Vector2, dt: float) -> Vector2:
	var n := Vector2(-sin(dir), cos(dir))
	var acc: float = (gravity * p.gravity - joint_acc * p.inertia).dot(n) / length
	acc += p.stiffness * (goal - angle) - p.damping * vel - parent_rot_acc * p.inertia
	vel += acc * dt   # semi-implicit Euler: velocity first, then the angle with the new velocity
	return Vector2(angle + vel * dt, vel)


## Critically damped follow: `pos` chases `goal` with weight, never overshooting.
## Returns the new velocity; the caller adds `velocity * dt` to the position.
static func follow(pos: Vector2, vel: Vector2, goal: Vector2, speed: float, dt: float) -> Vector2:
	return vel + ((goal - pos) * speed * speed - vel * 2.0 * speed) * dt
