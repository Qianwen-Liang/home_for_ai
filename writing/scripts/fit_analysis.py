import math

k_vals = [1, 2, 3, 4, 5, 6, 7, 8]
y_vals = [3.0, 4.0, 5.5, 7.5, 9.5, 11.5, 13.5, 16.0]

# Model A: 2^(alpha*sqrt(k))
log2y = [math.log2(y) for y in y_vals]
sqk = [math.sqrt(k) for k in k_vals]
sx, sy = sum(sqk), sum(log2y)
sxy = sum(x*y for x,y in zip(sqk, log2y))
sx2 = sum(x*x for x in sqk)
n = 8
alpha = (n*sxy - sx*sy) / (n*sx2 - sx*sx)
c = (sy - alpha*sx) / n

print("=== Model A: 2^(alpha*sqrt(k)) ===")
print(f"alpha={alpha:.4f}, c={c:.4f}, base=2^c={2**c:.3f}")
print(f"y = {2**c:.3f} * 2^({alpha:.4f} * sqrt(k))")
ssr, sst = 0, sum((y - sy/n)**2 for y in y_vals)
preds_a = []
for i in range(8):
    p = 2**(alpha*sqk[i] + c)
    preds_a.append(p)
    ssr += (y_vals[i] - p)**2
    print(f"  k={k_vals[i]}: actual={y_vals[i]:.1f}, pred={p:.2f}, err={y_vals[i]-p:+.2f}")
r2_a = 1 - ssr/sst
print(f"R^2 = {r2_a:.4f}")

# Model B: a * b^k
log10y = [math.log10(y) for y in y_vals]
sk2 = sum(k*k for k in k_vals)
sk = sum(k_vals)
slogy = sum(log10y)
sk_logy = sum(k*l for k,l in zip(k_vals, log10y))
logb = (n*sk_logy - sk*slogy) / (n*sk2 - sk*sk)
loga = (slogy - logb*sk) / n

print("\n=== Model B: a * b^k ===")
print(f"b=10^{logb:.4f}={10**logb:.4f}, a=10^{loga:.4f}={10**loga:.3f}")
ssr, preds_b = 0, []
for i in range(8):
    p = 10**(loga + logb*k_vals[i])
    preds_b.append(p)
    ssr += (y_vals[i] - p)**2
    print(f"  k={k_vals[i]}: actual={y_vals[i]:.1f}, pred={p:.2f}, err={y_vals[i]-p:+.2f}")
r2_b = 1 - ssr/sst
print(f"R^2 = {r2_b:.4f}")

# Model C: a * k^p
logk = [math.log10(k) for k in k_vals]
slk = sum(logk)
slk2 = sum(x*x for x in logk)
slk_ly = sum(x*y for x,y in zip(logk, log10y))
p = (n*slk_ly - slk*slogy) / (n*slk2 - slk*slk)
loga_c = (slogy - p*slk) / n

print("\n=== Model C: a * k^p ===")
print(f"p={p:.4f}, a=10^{loga_c:.4f}={10**loga_c:.3f}")
ssr, preds_c = 0, []
for i in range(8):
    pred = 10**(loga_c + p*logk[i])
    preds_c.append(pred)
    ssr += (y_vals[i] - pred)**2
    print(f"  k={k_vals[i]}: actual={y_vals[i]:.1f}, pred={pred:.2f}, err={y_vals[i]-pred:+.2f}")
r2_c = 1 - ssr/sst
print(f"R^2 = {r2_c:.4f}")

print("\n=== FINAL COMPARISON ===")
print(f"Model A (2^(a*sqrt(k))):  R^2 = {r2_a:.4f}")
print(f"Model B (a * b^k):        R^2 = {r2_b:.4f}")
print(f"Model C (a * k^p):        R^2 = {r2_c:.4f}")
best = "A" if r2_a >= max(r2_b, r2_c) else ("B" if r2_b >= max(r2_a, r2_c) else "C")
print(f"Best: Model {best}")

# Check user's pure hypothesis: y = 2^sqrt(k)
print("\n=== User hypothesis: y = 2^sqrt(k) (pure, no fit) ===")
ssr = 0
for i in range(8):
    p = 2**sqk[i]
    ssr += (y_vals[i] - p)**2
    print(f"  k={k_vals[i]}: actual={y_vals[i]:.1f}, 2^sqrt={p:.2f}, err={y_vals[i]-p:+.2f}")
print(f"R^2 = {1-ssr/sst:.4f}")
