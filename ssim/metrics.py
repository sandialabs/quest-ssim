import enum
import math


@enum.unique
class ImprovementType(int, enum.Enum):
    Minimize = 0
    Maximize = 1
    SeekValue = 2


class Metric:

    def __init__(
            self,
            limit: float,
            objective: float,
            imp_type: ImprovementType,
            a=5.0,
            b=5.0,
            c=0.0,
            g=0.2
    ):
        self._limit = limit
        self._objective = objective
        self._imp_type = imp_type
        self._a = a
        self._b = b
        self._c = c
        self._g = g
        self._validate_inputs()

    def normalize(self, value: float):
        if self._imp_type == ImprovementType.Minimize:
            return self._normalize_for_minimization(value)

        if self._imp_type == ImprovementType.Maximize:
            return self._normalize_for_maximization(value)

        return self._normalize_for_seek_value(value)

    def _normalize_for_minimization(self, value: float):
        return self.__do_max_norm__(-value, -self._limit, -self._objective)

    def _normalize_for_maximization(self, value: float):
        return self.__do_max_norm__(value, self._limit, self._objective)

    def _normalize_for_seek_value(self, value: float):
        biz_lim = self._objective - (self._limit - self._objective)

        use_lim = min(self._limit, biz_lim) if value <= self._objective else \
            max(self._limit, biz_lim)

        if value <= self._objective:
            return self.__do_max_norm__(value, use_lim, self._objective)

        return self.__do_max_norm__(-value, -use_lim, -self._objective)

    def _violated(self, norm_val: float):
        return -(self._a * norm_val * norm_val) / 2.0 + self._b * norm_val + self._c

    def _feasible(self, norm_val: float):
        d = self._d()
        return d * math.sqrt(norm_val + self._f(d)) + self._c - self._psi(d)

    def _super_optimal(self, norm_val: float):
        h = self._h(self._d())
        return self._g * math.sqrt(norm_val + h - 1.0) - self._phi(h) + 1.0

    def _d(self):
        x = 1.0 - 2.0 * self._c + self._c * self._c
        y = self._c + self._b - 1.0
        return math.sqrt(self._b * x / y)

    def _f(self, d: float):
        val = d / (2.0 * self._b)
        return val * val

    def _psi(self, d: float):
        return (d * d) / (2.0 * self._b)

    def _h(self, d: float):
        return (self._g * self._g * (self._f(d) + 1.0)) / (d * d)

    def _phi(self, h: float):
        return self._g * math.sqrt(h)

    def __do_max_norm__(self, value: float, limit: float, objective: float):
        resp_norm = (value - limit) / (objective - limit)

        if value < limit:
            return self._violated(resp_norm)
        if value < self._objective:
            return self._feasible(resp_norm)
        return self._super_optimal(resp_norm)

    def _validate_inputs(self):
        if self._imp_type == ImprovementType.Minimize:
            assert self._limit > self._objective, \
                "Limit must be greater than objective for minimization"

        elif self._imp_type == ImprovementType.Maximize:
            assert self._limit < self._objective, \
                "Limit must be less than objective for maximization"

        else:
            assert self._limit != self._objective, \
                "Limit cannot be equal to objective."


class MetricAccumulator:

    def __init__(self, m: Metric):
        self._metric = m
        self._accumulated = 0.0
        self._total_time = 0.0

    def accumulate(self, value: float, d_time: float):
        met_val = self._metric.normalize(value)
        self._total_time += d_time
        self._accumulated += d_time * met_val

    @property
    def accumulated_value(self):
        return self._accumulated

    @property
    def total_time(self):
        return self._total_time

    @property
    def denormalized_value(self):
        return self._accumulated / self._total_time

    @property
    def metric(self):
        return self._metric


# if __name__ == "__main__":
#    m_ = Metric(1.05, 1.0, ImprovementType.Minimize)
#    m_.normalize(1.0)
