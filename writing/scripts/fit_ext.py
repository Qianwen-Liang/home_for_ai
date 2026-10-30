import math
alpha, c = 1.3658, 0.1509
print('Extension to godhood stages:')
for k in [9, 10]:
    y = 2**(alpha*math.sqrt(k)+c)
    print(f'  k={k} (Seq {10-k}): pred log-energy={y:.1f}')
print()
print('Step multipliers (energy):')
for i in range(1,8):
    r = 2**(alpha*(math.sqrt(i+1)-math.sqrt(i)))
    print(f'  k={i}->{i+1}: sqrt-gap={math.sqrt(i+1)-math.sqrt(i):.3f}, energy x{r:.2f}')
