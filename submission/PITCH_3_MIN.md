# Three-minute pitch

Delivery: about three minutes with brief pauses and recorded-demo gestures. Use saved footage/results rather than
promise that a fresh live attempt will succeed. Spoken script follows.

Our simulated humanoid could lift an eighty-eight-pound box and still drop an eleven-pound one.

That is the problem we are tackling with Humanoid Lift Lab: a working robot controller can fail when the load changes.

Think about a small workshop, a stockroom, or a household. There is lifting work to do, but there is no robotics engineer standing beside the robot to tune every new box. Trying changes on hardware adds the risk of a dropped load or a damaged machine.

We are starting with one concrete task: adapting an in-place lift before deployment.

Here is the loop. We give the robot a controller and a payload. MuJoCo simulates the attempt and records what happened: grip slip, balance, joint effort, lift height, and hold time. We render that trajectory into video.

Gemini Argon receives the controller, video, numerical evidence, and attempt history. It explains the failure and writes a revised Python program over our documented motion API. Then we execute the revision and measure it again.

The important part is that Argon does not grade its own work. A deterministic scorer checks whether the box rises, stays up, avoids a fall or drop, and remains within the balance-assistance budget.

Let me show the recorded example. The reference controller drops the eleven-pound tote. Argon proposes grip and clearance changes. The revised controller lifts that same payload about sixty-nine centimeters and holds it for almost five seconds.

Across eight tested weights, from eleven to eighty-eight pounds, the video-feedback run improved from seven passes to eight after four revision rounds. We ran a telemetry-only comparison, and it also reached eight out of eight. That supports controller adaptation; it does not yet show that video beats telemetry.

We also learned that more iterations can make things worse. Our keep-best loop preserves stronger candidates, and the live demo checks previously working loads alongside the requested one. You can inspect what Argon received, its timestamped diagnosis, and the exact code diff.

An optional memory layer retains guidance linked to successful development evidence. A separate voice companion lets you ask questions about saved results and hear the explanation through Gemini speech generation.

Today, this is a modified, assisted simulation prototype. The results are development cases, and the next step is held-out conditions and hardware validation.

The product direction is a controller-adaptation workbench for robotics teams: make a change, show the evidence, and verify whether the robot actually improved.
