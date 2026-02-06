import math

class LowPassFilter:
    def __init__(self, alpha):
        self.__setAlpha(alpha)
        self.y = None
        self.s = None

    def __setAlpha(self, alpha):
        alpha = float(alpha)
        if alpha <= 0 or alpha > 1.0:
            raise ValueError("alpha should be in (0.0, 1.0]")
        self.alpha = alpha

    def filter(self, value, timestamp=None, alpha=None):
        if alpha: self.__setAlpha(alpha)
        if self.y is None:
            s = value
        else:
            s = self.alpha * value + (1.0 - self.alpha) * self.s
        self.y = value
        self.s = s
        return s

class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.first_time = True
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff
        self._dx = 0
        self._x_filt = LowPassFilter(alpha=1)
        self._dx_filt = LowPassFilter(alpha=1)
        self._t_prev = None

    def __call__(self, x, t):
        if self._t_prev is None:
            self._t_prev = t
            self._x_filt.filter(x)
            return x
        t_e = t - self._t_prev
        if t_e <= 0: return self._x_filt.s 
        self._t_prev = t
        alpha_d = self.__alpha(t_e, self._d_cutoff)
        dx = (x - self._x_filt.y) / t_e
        dx_hat = self._dx_filt.filter(dx, alpha=alpha_d)
        cutoff = self._min_cutoff + self._beta * abs(dx_hat)
        alpha = self.__alpha(t_e, cutoff)
        return self._x_filt.filter(x, alpha=alpha)

    def __alpha(self, t_e, cutoff):
        r = 2 * math.pi * cutoff * t_e
        return r / (r + 1)