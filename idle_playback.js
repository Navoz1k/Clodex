const claudeIdlePause = 8000;
const claudeIdlePool = [
    ...claudeGroups.idle, ...claudeGroups.rare, ...claudeGroups.veryRare, ...claudeGroups.legendary,
];
const claudeRepeatingIdle = new Set([
    '6035163756575596657', '6035238909913341713', '6035132678192243846',
    '6035299035160518638', '6035103867551624290', '6035096372833693925',
]);

function claudeChooseIdle(roll, equalOdds) {
    if (equalOdds) return claudeIdlePool[Math.floor(roll * claudeIdlePool.length)];
    const ticket = Math.floor(roll * 1_000_000);
    if (ticket < 954_900) return claudeGroups.idle[0];
    if (ticket < 994_900) {
        return claudeGroups.rare[Math.floor((ticket - 954_900) / 8_000)];
    }
    if (ticket < 999_900) {
        return claudeGroups.veryRare[Math.floor((ticket - 994_900) / 1_250)];
    }
    return claudeGroups.legendary[0];
}

function claudePlayResting(node, state, reduced, rows, alternate) {
    let frameTimer;
    const ordinary = claudeGroups.idle[0];

    function play(id, done, cycles = 1) {
        window.clearTimeout(frameTimer);
        const clip = claudeClips[id];
        const frameTime = clip.duration / clip.frames;
        node.style.backgroundImage = 'url(' + clip.image + ')';
        node.style.backgroundSize = '800% ' + clip.rows * 100 + '%';

        function show(index) {
            const x = index % 8 / 7 * 100;
            const y = Math.floor(index / 8) / (clip.rows - 1) * 100;
            node.style.backgroundPosition = x + '% ' + y + '%';
            if (!reduced) {
                frameTimer = window.setTimeout(() => {
                    if (index + 1 < clip.frames) show(index + 1);
                    else if (done && --cycles === 0) done();
                    else show(0);
                }, frameTime);
            }
        }
        show(0);
    }

    function startIdle() {
        play(ordinary, () => {
            node.style.backgroundPosition = '0% 0%';
            frameTimer = window.setTimeout(() => {
                const next = claudeChooseIdle(Math.random(), claudeEqualIdleOdds);
                if (next === ordinary) startIdle();
                else {
                    const cycles = claudeRepeatingIdle.has(next) ? 3 + Math.floor(Math.random() * 3) : 1;
                    play(next, startIdle, cycles);
                }
            }, claudeIdlePause);
        });
    }

    if (state === 'running') {
        play(claudeGroups.running[alternate ? 1 : 0]);
    } else if (state === 'approval') {
        play(claudeGroups.approval[0]);
    } else if (state === 'review') {
        const success = claudeGroups.success[!reduced && Math.random() >= 0.5 ? 1 : 0];
        play(success, startIdle);
    } else if (state === 'failed') {
        const frames = f.failed;
        function showFailure(index) {
            const frame = frames[index];
            node.style.backgroundPosition = v(frame, rows);
            if (!reduced) {
                frameTimer = window.setTimeout(
                    () => index + 1 < frames.length ? showFailure(index + 1) : startIdle(),
                    frame.frameDurationMs,
                );
            }
        }
        showFailure(0);
    } else {
        startIdle();
    }

    return () => {
        window.clearTimeout(frameTimer);
    };
}
