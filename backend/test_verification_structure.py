#!/usr/bin/env python3
"""测试新的verification_result嵌套结构是否能被正确处理"""

import json
import sys

# 模拟SaveFindings的过滤逻辑
def check_finding_structure(finding):
    """验证finding是否满足SaveFindings的要求"""
    
    issues = []
    
    # 检查1: verification_result是否存在且为dict
    verification_result_payload_input = finding.get("verification_result")
    if not isinstance(verification_result_payload_input, dict):
        issues.append("missing_verification_result: finding.get('verification_result') is not dict")
        return issues
    
    # 检查2: 从verification_result中提取必需字段
    authenticity_raw = (
        finding.get("authenticity")
        or finding.get("verdict")
        or verification_result_payload_input.get("authenticity")
        or verification_result_payload_input.get("verdict")
    )
    reachability_raw = (
        finding.get("reachability")
        or verification_result_payload_input.get("reachability")
    )
    evidence_raw = (
        finding.get("verification_details")
        or finding.get("verification_evidence")
        or verification_result_payload_input.get("verification_details")
        or verification_result_payload_input.get("verification_evidence")
        or verification_result_payload_input.get("evidence")
    )
    
    if not authenticity_raw:
        issues.append("missing_authenticity: no verdict found")
    if not reachability_raw:
        issues.append("missing_reachability: no reachability found")
    if not evidence_raw:
        issues.append("missing_evidence: no verification_evidence found")
    
    if issues:
        return issues
    
    # 检查3: verdict值范围
    authenticity = str(authenticity_raw).strip().lower()
    if authenticity not in {"confirmed", "likely", "false_positive"}:
        issues.append(f"invalid_verdict: {authenticity} not in valid values")
    
    # 检查4: reachability值范围
    reachability = str(reachability_raw).strip().lower()
    if reachability not in {"reachable", "likely_reachable", "unreachable"}:
        issues.append(f"invalid_reachability: {reachability} not in valid values")
    
    return issues


# 测试用例1: 老格式（verification_result不存在）
old_format_finding = {
    "file_path": "server/app.py",
    "line_start": 36,
    "line_end": 36,
    "title": "ReDoS漏洞",
    "verdict": "confirmed",
    "confidence": 0.92,
    "reachability": "reachable",
    "verification_evidence": "通过fuzzing验证",
    "cwe_id": "CWE-1333",
}

# 测试用例2: 新格式（带verification_result嵌套dict）
new_format_finding = {
    "file_path": "server/app.py",
    "line_start": 36,
    "line_end": 36,
    "title": "ReDoS漏洞",
    "cwe_id": "CWE-1333",
    "verification_result": {
        "verdict": "confirmed",
        "confidence": 0.92,
        "reachability": "reachable",
        "verification_evidence": "通过fuzzing验证"
    },
    "suggestion": "使用regex库替代re.search"
}

# 测试用例3: 混合格式（两个位置都有）
hybrid_format_finding = {
    "file_path": "server/app.py",
    "line_start": 36,
    "line_end": 36,
    "title": "ReDoS漏洞",
    "cwe_id": "CWE-1333",
    "verdict": "confirmed",
    "confidence": 0.92,
    "reachability": "reachable",
    "verification_evidence": "通过fuzzing验证",
    "verification_result": {
        "verdict": "confirmed",
        "confidence": 0.92,
        "reachability": "reachable",
        "verification_evidence": "通过fuzzing验证"
    },
    "suggestion": "使用regex库替代re.search"
}

# 测试缺失verification_result的情况
missing_verification_result = {
    "file_path": "server/app.py",
    "line_start": 36,
    "line_end": 36,
    "title": "ReDoS漏洞",
    "cwe_id": "CWE-1333",
    "suggestion": "修复建议"
}

# 运行测试
test_cases = [
    ("老格式 (findings层级)", old_format_finding),
    ("新格式 (verification_result嵌套)", new_format_finding),
    ("混合格式 (两层都有)", hybrid_format_finding),
    ("缺失verification_result", missing_verification_result),
]

all_pass = True
for test_name, finding in test_cases:
    issues = check_finding_structure(finding)
    status = "✓ PASS" if not issues else "✗ FAIL"
    print(f"\n{status}: {test_name}")
    if issues:
        for issue in issues:
            print(f"  - {issue}")
        all_pass = False
    else:
        print(f"  - 所有检查通过")

print("\n" + "="*60)
if all_pass:
    print("✅ 结论: 新格式可以正确通过SaveFindings的验证!")
    sys.exit(0)
else:
    print("❌ 警告: 某些格式无法通过SaveFindings的验证")
    print("\n建议: 系统提示词应该引导LLM输出' 新格式'")
    sys.exit(1)
