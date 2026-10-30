import math
alpha, c = 1.35, 0.08
print("Power curve:")
for k in range(1, 9):
    y = 2**(alpha*math.sqrt(k) + c)
    print(f"  Tier {k}: logE={y:.1f}")
print("Step multipliers:")
for i in range(1, 8):
    r = 2**(alpha*(math.sqrt(i+1)-math.sqrt(i)))
    print(f"  {i}->{i+1}: x{r:.2f}")
