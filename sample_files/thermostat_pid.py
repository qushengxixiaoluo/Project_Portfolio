"""PID 温控模块 — smart-thermostat 项目"""

KP = 2.4
KI = 0.8
KD = 1.2
SETPOINT_DEFAULT = 60.0  # 摄氏度


class PIDController:
    def __init__(self, kp=KP, ki=KI, kd=KD, setpoint=SETPOINT_DEFAULT):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.setpoint = setpoint
        self._prev_error = 0.0
        self._integral = 0.0

    def update(self, measured: float, dt: float) -> float:
        error = self.setpoint - measured
        self._integral += error * dt
        derivative = (error - self._prev_error) / dt if dt > 0 else 0.0
        self._prev_error = error
        output = self.kp * error + self.ki * self._integral + self.kd * derivative
        return max(0.0, min(100.0, output))  # PWM 占空比 0-100%
