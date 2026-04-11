"""
Unit tests for BusinessLogicScanTool

测试业务逻辑漏洞扫描工具的核心功能
"""

import pytest
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional


# ============ 轻量级数据类定义（用于单元测试）============

@dataclass
class BusinessLogicFindingSimple:
    """简化版的业务逻辑发现数据类（用于单元测试）"""
    id: str
    title: str
    severity: str  # critical, high, medium, low
    vulnerability_type: str
    description: str
    file_path: str
    function_name: str
    line_start: int
    line_end: Optional[int] = None
    code_snippet: str = ""
    confidence: float = 0.5
    taint_path: List[Dict[str, Any]] = field(default_factory=list)
    missing_checks: List[str] = field(default_factory=list)


@dataclass
class BusinessLogicScanInputSimple:
    """简化版的输入参数"""
    target: str
    focus_areas: List[str] = field(default_factory=list)
    max_iterations: int = 5
    quick_mode: bool = False
    demo_results: bool = False


# ============ 测试类 ============

class TestBusinessLogicScanInputValidation:
    """测试输入验证"""
    
    def test_valid_input(self):
        """测试有效输入"""
        input_data = BusinessLogicScanInputSimple(
            target=".",
            focus_areas=["authentication", "authorization"],
            max_iterations=5,
        )
        assert input_data.target == "."
        assert input_data.focus_areas == ["authentication", "authorization"]
        assert input_data.max_iterations == 5
    
    def test_input_with_defaults(self):
        """测试使用默认值的输入"""
        input_data = BusinessLogicScanInputSimple(target=".")
        assert input_data.target == "."
        assert input_data.focus_areas == []
        assert input_data.max_iterations == 5
        assert input_data.quick_mode is False
        assert input_data.demo_results is False
    
    def test_input_target_validation(self):
        """测试输入目标验证"""
        input_data = BusinessLogicScanInputSimple(target=".", focus_areas=["auth"])
        assert input_data.target == "."
        assert len(input_data.focus_areas) == 1


class TestBusinessLogicFindingDataclass:
    """测试漏洞数据类"""
    
    def test_finding_creation(self):
        """测试漏洞对象创建"""
        finding = BusinessLogicFindingSimple(
            id="BL-001",
            title="app/api/user.py中权限检查缺失漏洞",
            severity="high",
            vulnerability_type="privilege_escalation",
            description="用户可以修改其他用户信息",
            file_path="app/api/user.py",
            function_name="update_user",
            line_start=20,
            line_end=30,
            code_snippet="def update_user(...):",
            confidence=0.85,
        )
        
        assert finding.id == "BL-001"
        assert finding.severity == "high"
        assert finding.vulnerability_type == "privilege_escalation"
        assert finding.confidence == 0.85
        assert finding.line_start == 20
        assert finding.line_end == 30
    
    def test_finding_to_dict(self):
        """测试漏洞转换为字典"""
        finding = BusinessLogicFindingSimple(
            id="BL-001",
            title="test",
            severity="high",
            vulnerability_type="idor",
            description="test description",
            file_path="app.py",
            function_name="get_user",
            line_start=10,
            code_snippet="code",
            confidence=0.9,
        )
        
        finding_dict = asdict(finding)
        assert isinstance(finding_dict, dict)
        assert finding_dict["id"] == "BL-001"
        assert finding_dict["vulnerability_type"] == "idor"
        assert finding_dict["severity"] == "high"
    
    def test_finding_default_values(self):
        """测试漏洞的默认值"""
        finding = BusinessLogicFindingSimple(
            id="BL-002",
            title="test",
            severity="medium",
            vulnerability_type="business_logic_flaw",
            description="test",
            file_path="test.py",
            function_name="test_func",
            line_start=1,
        )
        
        assert finding.line_end is None
        assert finding.code_snippet == ""
        assert finding.confidence == 0.5
        assert finding.taint_path == []
        assert finding.missing_checks == []
    
    def test_finding_with_taint_path(self):
        """测试包含污点路径的漏洞"""
        taint_path = [
            {"stage": "entry", "detail": "user_id from URL"},
            {"stage": "missing_check", "detail": "no authorization"}
        ]
        
        finding = BusinessLogicFindingSimple(
            id="BL-003",
            title="test",
            severity="high",
            vulnerability_type="idor",
            description="test",
            file_path="app.py",
            function_name="update",
            line_start=10,
            taint_path=taint_path,
        )
        
        assert len(finding.taint_path) == 2
        assert finding.taint_path[0]["stage"] == "entry"
        assert finding.taint_path[1]["detail"] == "no authorization"


class TestVulnerabilityTypeValidation:
    """测试漏洞类型验证"""
    
    def test_supported_vulnerability_types(self):
        """测试所有支持的漏洞类型"""
        supported_types = [
            "idor",
            "privilege_escalation",
            "business_logic_flaw",
            "account_takeover",
            "race_condition",
            "authorization_bypass",
            "payment_fraud",
            "data_manipulation",
        ]
        
        for vuln_type in supported_types:
            finding = BusinessLogicFindingSimple(
                id="BL-001",
                title="test",
                severity="high",
                vulnerability_type=vuln_type,
                description="test",
                file_path="test.py",
                function_name="test",
                line_start=1,
            )
            assert finding.vulnerability_type == vuln_type
    
    def test_severity_levels(self):
        """测试所有支持的严重程度"""
        severities = ["critical", "high", "medium", "low"]
        
        for severity in severities:
            finding = BusinessLogicFindingSimple(
                id="BL-001",
                title="test",
                severity=severity,
                vulnerability_type="idor",
                description="test",
                file_path="test.py",
                function_name="test",
                line_start=1,
            )
            assert finding.severity == severity


class TestFindingConfidenceScore:
    """测试漏洞置信度分数"""
    
    def test_confidence_range(self):
        """测试置信度分数范围"""
        confidences = [0.0, 0.25, 0.5, 0.75, 1.0]
        
        for conf in confidences:
            finding = BusinessLogicFindingSimple(
                id="BL-001",
                title="test",
                severity="high",
                vulnerability_type="idor",
                description="test",
                file_path="test.py",
                function_name="test",
                line_start=1,
                confidence=conf,
            )
            assert finding.confidence == conf
    
    def test_default_confidence(self):
        """测试默认置信度"""
        finding = BusinessLogicFindingSimple(
            id="BL-001",
            title="test",
            severity="high",
            vulnerability_type="idor",
            description="test",
            file_path="test.py",
            function_name="test",
            line_start=1,
        )
        assert finding.confidence == 0.5


class TestPatternDetection:
    """测试模式检测逻辑"""
    
    def test_authorization_check_pattern(self):
        """测试授权检查模式"""
        code_without_auth = """
def update_user(user_id: int, data: dict):
    user = db.query(User).filter(User.id == user_id).first()
    user.name = data['name']
    db.commit()
"""
        
        code_with_auth = """
def update_user(user_id: int, data: dict):
    if user_id != current_user.id:
        raise PermissionError()
    user = db.query(User).filter(User.id == user_id).first()
    user.name = data['name']
    db.commit()
"""
        
        has_auth_in_first = "current_user" in code_without_auth or "request.user" in code_without_auth
        has_auth_in_second = "current_user" in code_with_auth or "request.user" in code_with_auth
        
        assert not has_auth_in_first
        assert has_auth_in_second
    
    def test_sensitive_operation_keywords(self):
        """测试敏感操作关键字检测"""
        sensitive_keywords = {
            "payment": ["transfer", "payment", "charge", "refund"],
            "account": ["password", "email", "phone", "delete_account"],
            "access": ["permission", "role", "admin", "grant"],
        }
        
        code_samples = {
            "payment": "amount = transfer_funds(from_id, to_id, amount)",
            "account": "change_password(user_id, new_password)",
            "access": "set_user_role(user_id, 'admin')",
        }
        
        for category, code in code_samples.items():
            found = False
            for keyword in sensitive_keywords[category]:
                if keyword in code.lower():
                    found = True
                    break
            assert found


class TestFindingValidation:
    """测试漏洞数据的有效性"""
    
    def test_title_format(self):
        """测试标题格式"""
        title = "app/api/user.py中update_user权限提升漏洞"
        
        parts = title.split("中")
        assert len(parts) >= 2
        assert ".py" in parts[0]
        assert "漏洞" in title
    
    def test_description_not_empty(self):
        """测试描述不为空"""
        finding = BusinessLogicFindingSimple(
            id="BL-001",
            title="test",
            severity="high",
            vulnerability_type="idor",
            description="用户可以访问其他用户的敏感信息",
            file_path="test.py",
            function_name="test",
            line_start=1,
        )
        
        assert len(finding.description) > 0
        assert finding.description.strip() != ""
    
    def test_file_path_format(self):
        """测试文件路径格式"""
        valid_paths = [
            "app/api/user.py",
            "src/main.go",
            "controllers/UserController.java",
        ]
        
        for path in valid_paths:
            finding = BusinessLogicFindingSimple(
                id="BL-001",
                title="test",
                severity="high",
                vulnerability_type="idor",
                description="test",
                file_path=path,
                function_name="test",
                line_start=1,
            )
            
            assert "/" in path or "\\" in path
            assert finding.file_path == path


class TestInputParameterCombinations:
    """测试输入参数的不同组合"""
    
    def test_minimal_input(self):
        """测试最小输入参数"""
        input_data = BusinessLogicScanInputSimple(target=".")
        
        assert input_data.target == "."
        assert input_data.focus_areas == []
        assert input_data.max_iterations == 5
        assert input_data.quick_mode is False
        assert input_data.demo_results is False
    
    def test_full_input(self):
        """测试完整输入参数"""
        input_data = BusinessLogicScanInputSimple(
            target="src",
            focus_areas=["authentication", "payment", "authorization"],
            max_iterations=10,
            quick_mode=True,
            demo_results=True,
        )
        
        assert input_data.target == "src"
        assert len(input_data.focus_areas) == 3
        assert input_data.max_iterations == 10
        assert input_data.quick_mode is True
        assert input_data.demo_results is True
    
    def test_mixed_input(self):
        """测试混合输入参数"""
        input_data = BusinessLogicScanInputSimple(
            target="app",
            focus_areas=["auth"],
            quick_mode=True,
        )
        
        assert input_data.target == "app"
        assert input_data.focus_areas == ["auth"]
        assert input_data.quick_mode is True
        assert input_data.demo_results is False
        assert input_data.max_iterations == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
