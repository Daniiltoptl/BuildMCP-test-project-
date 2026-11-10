n = 0
for x in range(-24, 25, 7):
    for z in range(-24, 25, 7):
        if x * x + z * z <= 24 ** 2 and str(S.get(x, 67, z)).endswith("air"):
            S.set(x, 67, z, "light[level=12]"); n += 1
print("lights", n)
finalize()
print(str(lint())[:1500])
