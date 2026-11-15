//
// MatlabRng.h - bit-exact reproduction of MATLAB's rng(seed,'twister') streams.
//
// Verified against MATLAB R2026a (matlab_reference/data/rng_probe.txt):
//   rng(seed,'twister')  -> MT19937 init_genrand(seed)          (std::mt19937::seed)
//   rand()               -> 53-bit double: (a*2^26 + b) / 2^53, a = u32>>5, b = u32>>6
//   randi(n)             -> ceil(rand()*n), consumes exactly one rand() (also for n == 1)
//   rand(m,n)            -> column-major fill, one rand() per element
//
#ifndef __PERIYAR_MATLABRNG_H
#define __PERIYAR_MATLABRNG_H

#include <cmath>
#include <cstdint>
#include <random>

class MatlabTwister
{
  private:
    std::mt19937 gen;
    uint64_t draws = 0;

  public:
    explicit MatlabTwister(uint32_t seed = 5489) { gen.seed(seed); }
    void seed(uint32_t s) { gen.seed(s); draws = 0; }
    double rand()
    {
        uint32_t a = gen() >> 5, b = gen() >> 6;
        draws++;
        return (a * 67108864.0 + b) * (1.0 / 9007199254740992.0);
    }
    int randi(int n) { return (int)std::ceil(rand() * n); }
    uint64_t numDraws() const { return draws; }
};

#endif
