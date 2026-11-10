def isair(x, y, z): return str(S.get(x, y, z)).endswith("air")
def drop(cols, ylo, yhi):
    n = 0
    for (x, z) in cols:
        if not isair(x, ylo - 1, z): continue           # something already stands on the ground here
        for y in range(ylo, yhi + 1):
            b = S.get(x, y, z)
            S.set(x, y - 1, z, b); n += 0 if str(b).endswith("air") else 1
        S.set(x, yhi, z, "air")
    return n
GY = 67
cols = {(x, z) for x in range(136, 143) for z in range(-3, 3)} | {(x, z) for x in range(140, 149) for z in range(10, 16)}
n1 = drop(sorted(cols), GY + 2, GY + 9)
GZ = 66
n2 = drop([(86, z) for z in range(108, 113)], GZ + 3, GZ + 4)
# soft light over the dais and its steps
nl = 0
for rad, cnt in ((22, 12), (33, 18)):
    for j in range(cnt):
        a = 2 * math.pi * (j + 0.5) / cnt
        x, z = int(round(rad * math.cos(a))), int(round(rad * math.sin(a)))
        if isair(x, 72, z): S.set(x, 72, z, "light[level=13]"); nl += 1
print("dropped", n1, n2, "lights", nl)
finalize()
issues = lint()
print(issues if isinstance(issues, str) else str(issues)[:3000])
