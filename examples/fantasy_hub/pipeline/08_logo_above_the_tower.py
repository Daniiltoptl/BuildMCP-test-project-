face = P.gradient(["ochre_froglight", "gold_block", "orange_concrete"], axis="y", start=144, end=137)
res = text.text3d("BUILDMCP", at=(0, 137, -32), facing="south", scale=1, depth=2, face=face,
                  side="orange_terracotta", outline="black_concrete", outline_depth=1)
print(S.bbox(), res["all"].bbox)