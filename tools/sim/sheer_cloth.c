// SHEER physics prototype kernel (C + OpenMP; reference for the Unity compute shader).
// One call = n substeps of the stocking lattice of one leg.  Per node, gather style (each node reads its 8
// neighbours and writes only itself; ping-pong buffers), exactly what a compute kernel does.
//
//   springs     u (course, periodic), v (wale), 2 diagonals per cell; tension = A * f(L / L0) with the J-curve
//               f = (lam - 1) + S * max(0, lam - lock)^2, weak in compression; ladder cells carry only slack floats.
//   integrator  dynamic relaxation with locally scaled masses m = alpha * sum(tangent stiffness)  (dt = 1)
//   contact     radial height field R(theta, y) about the leg axis; exact Coulomb friction at the velocity level.
#include <math.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

typedef struct {
    int NV, NU;
    float y0, dy;
    float lock_u, lock_v, lock_d, Su, Sv, Sd, comp;
    float lad_slack, lad_k, lad_lock, Sl;
    float mu_s, mu_k, alpha, damp, visc, quench, mix, cfl, kfloor, trust;
    float gather;
    float hand[3];
} Params;

static inline void law(float lam, float lock, float S, float comp, float* f, float* df)
{
    float e = lam - 1.f;
    if (e >= 0.f) { float o = lam > lock ? lam - lock : 0.f; *f = e + S * o * o; *df = 1.f + 2.f * S * o; }
    else { *f = comp * e; *df = comp; }
}

// phi = rho - R (negative inside), outward unit normal n, radial unit er (xz)
static inline float collide(const Params* P, const float* Rtex, const float* axtex, const float* p, float* n, float* er)
{
    int NV = P->NV, NU = P->NU;
    float fy = (p[1] - P->y0) / P->dy; if (fy < 0.f) fy = 0.f; if (fy > NV - 1.001f) fy = NV - 1.001f;
    int j0 = (int)fy; float a = fy - j0;
    const float* A0 = axtex + 4 * j0; const float* A1 = A0 + 4;
    float ax = A0[0] + (A1[0] - A0[0]) * a, az = A0[1] + (A1[1] - A0[1]) * a;
    float axp = A0[2] + (A1[2] - A0[2]) * a, azp = A0[3] + (A1[3] - A0[3]) * a;
    float dx = p[0] - ax, dz = p[2] - az;
    float rho = sqrtf(dx * dx + dz * dz); if (rho < 1e-7f) rho = 1e-7f;
    float th = atan2f(dx, dz) * (1.f / 6.283185307f); th -= floorf(th);
    float fi = th * NU; int i0 = (int)fi; float b = fi - i0; if (i0 >= NU) i0 -= NU; int i1 = i0 + 1; if (i1 >= NU) i1 = 0;
    const float* r00 = Rtex + 3 * (j0 * NU + i0); const float* r01 = Rtex + 3 * (j0 * NU + i1);
    const float* r10 = r00 + 3 * NU; const float* r11 = r01 + 3 * NU;
    float w00 = (1 - a) * (1 - b), w01 = (1 - a) * b, w10 = a * (1 - b), w11 = a * b;
    float R = r00[0] * w00 + r01[0] * w01 + r10[0] * w10 + r11[0] * w11;
    float Rth = r00[1] * w00 + r01[1] * w01 + r10[1] * w10 + r11[1] * w11;
    float Ry = r00[2] * w00 + r01[2] * w01 + r10[2] * w10 + r11[2] * w11;
    float erx = dx / rho, erz = dz / rho, etx = erz, etz = -erx, q = Rth / rho;
    float gx = erx - q * etx, gz = erz - q * etz;
    float gy = -(erx * axp + erz * azp) - Ry + q * (etx * axp + etz * azp);
    float gl = 1.f / sqrtf(gx * gx + gy * gy + gz * gz);
    n[0] = gx * gl; n[1] = gy * gl; n[2] = gz * gl; er[0] = erx; er[1] = erz;
    return rho - R;
}

typedef struct { float F0, F1, F2, K, Lmin; int n; float e[8][3]; float allow[8]; const float* vn[8]; } Acc;

static inline void add_spring(Acc* a, const float* p, const float* q, const float* vq, float l0, int mode,
                              const Params* P, float A, float Al, float lock, float S)
{
    float d0 = q[0] - p[0], d1 = q[1] - p[1], d2 = q[2] - p[2];
    float L = sqrtf(d0 * d0 + d1 * d1 + d2 * d2); if (L < 1e-9f) L = 1e-9f;
    if (A + Al > 0.f && L < a->Lmin) a->Lmin = L;
    float lam = L / l0, f, df, T, kt;
    law(lam, lock, S, P->comp, &f, &df);
    T = A * f; kt = A * df / l0;
    if (mode == 1 && Al > 0.f)        // course spring next to ladder cells: slack floats
    {
        float fl, dfl; law(lam / P->lad_slack, P->lad_lock, P->Sl, 0.f, &fl, &dfl);
        T += Al * P->lad_k * fl; kt += Al * P->lad_k * dfl / (P->lad_slack * l0);
    }
    float s = T / L; a->F0 += d0 * s; a->F1 += d1 * s; a->F2 += d2 * s;
    float kg = T > 0.f ? s : 0.f; a->K += kt > kg ? kt : kg;
    // trust region: a thread may lengthen freely up to the point where it stiffens (lock / taut float) and from
    // there only by a small fraction of its natural length per substep (the tangent stiffness that sets the
    // mass knows nothing about the wall ahead)
    if (A + Al > 0.f)
    {
        float lk = A > 0.f ? lock * l0 : P->lad_slack * P->lad_lock * l0;
        float room = lk - L; if (room < 0.f) room = 0.f;
        int n = a->n++; float iL = 1.f / L;
        a->e[n][0] = d0 * iL; a->e[n][1] = d1 * iL; a->e[n][2] = d2 * iL;
        a->allow[n] = room + P->trust * (A > 0.f ? l0 : P->lad_slack * l0); a->vn[n] = vq;
    }
}
#define SPU(NB, E) add_spring(&A, p, x + 3 * (NB), v + 3 * (NB), Lu0[E], 1, P, Au_i[E], Au_l[E], P->lock_u, P->Su)
#define SPV(NB, E) add_spring(&A, p, x + 3 * (NB), v + 3 * (NB), Lv0[E], 0, P, Av[E], 0.f, P->lock_v, P->Sv)
#define SPD(NB, C) add_spring(&A, p, x + 3 * (NB), v + 3 * (NB), Ld0[C], 0, P, Ad[C], 0.f, P->lock_d, P->Sd)

// flags: 1 pinned, 2 hand-held (kinematic), 4 orphan (inside a hole)
void sheer_step(const Params* P, int nsub, float* xa, float* va, float* xb, float* vb,
                const float* Lu0, const float* Lv0, const float* Ld0,
                const float* Au_i, const float* Au_l, const float* Av, const float* Ad, const float* K0,
                const uint8_t* flags, const float* off, const float* Rtex, const float* axtex,
                float* Nn, const float* hand0, const float* hand1, float* hand_force)
{
    int NV = P->NV, NU = P->NU;
    float hf0 = 0, hf1 = 0, hf2 = 0;
    for (int it = 0; it < nsub; it++)
    {
        const float* x = (it & 1) ? xb : xa; const float* v = (it & 1) ? vb : va;
        float* xo = (it & 1) ? xa : xb; float* vo = (it & 1) ? va : vb;
        float ht = (it + 1.f) / nsub;
        float hand[3] = { hand0[0] + (hand1[0] - hand0[0]) * ht, hand0[1] + (hand1[1] - hand0[1]) * ht, hand0[2] + (hand1[2] - hand0[2]) * ht };
        int last = it == nsub - 1;
        hf0 = hf1 = hf2 = 0;
        #pragma omp parallel for schedule(static) reduction(+:hf0,hf1,hf2)
        for (int j = 0; j < NV; j++)
            for (int i = 0; i < NU; i++)
            {
                int k = j * NU + i, ip = i + 1 < NU ? i + 1 : 0, im = i > 0 ? i - 1 : NU - 1;
                const float* p = x + 3 * k;
                Acc A; A.F0 = A.F1 = A.F2 = A.K = 0.f; A.Lmin = 1e9f; A.n = 0;
                SPU(j * NU + ip, k); SPU(j * NU + im, j * NU + im);
                if (j < NV - 1) { SPV(k + NU, k); SPD((j + 1) * NU + ip, k); SPD((j + 1) * NU + im, j * NU + im); }
                if (j > 0) { SPV(k - NU, k - NU); SPD((j - 1) * NU + ip, (j - 1) * NU + i); SPD((j - 1) * NU + im, (j - 1) * NU + im); }
                float F0 = A.F0, F1 = A.F1, F2 = A.F2, K = A.K;
                uint8_t fl = flags[k];
                // fictitious mass from the tangent stiffness; a node whose threads are all slack keeps a fraction of its
                // intact stiffness as mass (otherwise the slightest force would throw it)
                { float kf = P->kfloor * K0[k]; if (K < kf) K = kf; }
                float m = P->alpha * K; if (m < 1e-12f) m = 1e-12f;
                float n[3], er[2];
                float phi = collide(P, Rtex, axtex, p, n, er);
                int touching = phi < 2e-5f;
                // neighbours' velocities (internal friction)
                const float* vc = v + 3 * k; const float* vl = v + 3 * (j * NU + im); const float* vr = v + 3 * (j * NU + ip);
                const float* vd = v + 3 * (j > 0 ? k - NU : k); const float* vu = v + 3 * (j < NV - 1 ? k + NU : k);
                float w0 = 1.f - P->damp, vs = P->visc;
                float v0 = vc[0] * w0, v1 = vc[1] * w0, v2 = vc[2] * w0;
                v0 += vs * (0.25f * (vl[0] + vr[0] + vd[0] + vu[0]) * w0 - v0);
                v1 += vs * (0.25f * (vl[1] + vr[1] + vd[1] + vu[1]) * w0 - v1);
                v2 += vs * (0.25f * (vl[2] + vr[2] + vd[2] + vu[2]) * w0 - v2);
                float im_ = 1.f / m;
                // overdamped relaxation (the knit and the skin dissipate everything): a node never keeps moving
                // against the force that acts on it, and its velocity is steered towards that force (per-node FIRE)
                {
                    float E0 = F0, E1 = F1, E2 = F2;
                    if (touching) { float Fn_ = F0 * n[0] + F1 * n[1] + F2 * n[2]; if (Fn_ < 0.f) { E0 -= Fn_ * n[0]; E1 -= Fn_ * n[1]; E2 -= Fn_ * n[2]; } }
                    float pw = v0 * E0 + v1 * E1 + v2 * E2;
                    if (pw <= 0.f) { float q = 1.f - P->quench; v0 *= q; v1 *= q; v2 *= q; }
                    else if (P->mix > 0.f)
                    {
                        float vl2 = sqrtf(v0 * v0 + v1 * v1 + v2 * v2), el = sqrtf(E0 * E0 + E1 * E1 + E2 * E2) + 1e-30f, g = P->mix * vl2 / el;
                        v0 = (1.f - P->mix) * v0 + g * E0; v1 = (1.f - P->mix) * v1 + g * E1; v2 = (1.f - P->mix) * v2 + g * E2;
                    }
                }
                v0 += F0 * im_; v1 += F1 * im_; v2 += F2 * im_;
                {   // no node travels more than a fraction of its shortest thread per substep
                    float vmax = P->cfl * A.Lmin, vl2 = v0 * v0 + v1 * v1 + v2 * v2;
                    if (vl2 > vmax * vmax) { float q = vmax / sqrtf(vl2); v0 *= q; v1 *= q; v2 *= q; }
                    for (int q = 0; q < A.n; q++)
                    {
                        const float* w = A.vn[q];                                                 // the far end's last velocity
                        float r = -((v0 - w[0]) * A.e[q][0] + (v1 - w[1]) * A.e[q][1] + (v2 - w[2]) * A.e[q][2]);   // lengthening rate of thread q
                        if (r > A.allow[q]) { float ex = r - A.allow[q]; v0 += ex * A.e[q][0]; v1 += ex * A.e[q][1]; v2 += ex * A.e[q][2]; }
                    }
                }
                float nn = 0.f;
                if (touching)
                {
                    float Fn = F0 * n[0] + F1 * n[1] + F2 * n[2];
                    float vn = v0 * n[0] + v1 * n[1] + v2 * n[2];
                    if (vn < 0.f) { v0 -= vn * n[0]; v1 -= vn * n[1]; v2 -= vn * n[2]; }
                    if (Fn < 0.f)
                    {
                        float vn2 = v0 * n[0] + v1 * n[1] + v2 * n[2];
                        float t0 = v0 - vn2 * n[0], t1 = v1 - vn2 * n[1], t2 = v2 - vn2 * n[2];
                        float tl = sqrtf(t0 * t0 + t1 * t1 + t2 * t2);
                        float N = -Fn * im_;
                        if (tl <= P->mu_s * N) { v0 = v1 = v2 = 0.f; }
                        else { float s = 1.f - P->mu_k * N / tl; if (s < 0.f) s = 0.f; v0 = t0 * s; v1 = t1 * s; v2 = t2 * s; }
                        nn = -Fn;
                    }
                }
                float x0, x1, x2;
                if (fl & 3)
                {
                    v0 = v1 = v2 = 0.f;
                    if (fl & 2) {
                        x0 = hand[0] + off[3 * k] * P->gather; x1 = hand[1] + off[3 * k + 1] * P->gather; x2 = hand[2] + off[3 * k + 2] * P->gather;
                        v0 = x0 - p[0]; v1 = x1 - p[1]; v2 = x2 - p[2];          // the neighbours see how the pinch moves
                        hf0 -= F0; hf1 -= F1; hf2 -= F2;
                    } else { x0 = p[0]; x1 = p[1]; x2 = p[2]; }
                }
                else if (fl & 4)
                {
                    const float* a = x + 3 * (j * NU + im); const float* b = x + 3 * (j * NU + ip);
                    const float* c = x + 3 * (j > 0 ? k - NU : k); const float* d = x + 3 * (j < NV - 1 ? k + NU : k);
                    x0 = 0.25f * (a[0] + b[0] + c[0] + d[0]); x1 = 0.25f * (a[1] + b[1] + c[1] + d[1]); x2 = 0.25f * (a[2] + b[2] + c[2] + d[2]);
                    v0 = v1 = v2 = 0.f;
                    float q[3] = { x0, x1, x2 }; float n2[3], e2[2];
                    float ph = collide(P, Rtex, axtex, q, n2, e2);
                    if (ph < 0.f) { x0 -= e2[0] * ph; x2 -= e2[1] * ph; }
                }
                else
                {
                    float q[3] = { p[0] + v0, p[1] + v1, p[2] + v2 }; float n2[3], e2[2];
                    float ph = collide(P, Rtex, axtex, q, n2, e2);
                    if (ph < 0.f) { q[0] -= e2[0] * ph; q[2] -= e2[1] * ph; }
                    x0 = q[0]; x1 = q[1]; x2 = q[2];
                }
                xo[3 * k] = x0; xo[3 * k + 1] = x1; xo[3 * k + 2] = x2;
                vo[3 * k] = v0; vo[3 * k + 1] = v1; vo[3 * k + 2] = v2;
                if (last && Nn) Nn[k] = touching ? nn : -1.f;
            }
    }
    hand_force[0] = hf0; hand_force[1] = hf1; hand_force[2] = hf2;
    if (nsub & 1) { memcpy(xa, xb, sizeof(float) * 3 * NV * NU); memcpy(va, vb, sizeof(float) * 3 * NV * NU); }
}
