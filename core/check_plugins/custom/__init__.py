# Custom checks - add your own checks here.
# They will be auto-discovered.
#
# Example:
#
# from core.checks.base import BaseCheck, CheckResult
#
# class MyCustomCheck(BaseCheck):
#     name = "My Check"
#     description = "Does something custom"
#     category = "custom"
#     default_phases = [3, 4]  # Testing and Final
#
#     def run(self, project_path: str, **kwargs) -> CheckResult:
#         # Your logic here
#         return CheckResult(self.name, True, "All good")
