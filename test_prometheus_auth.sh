#!/bin/bash

# Prometheus Authentication Test Suite
# Tests to ensure NO ACCESS is allowed without correct credentials
# NOTE: This script does NOT contain the correct password for security reasons

PROMETHEUS_URL="https://monitoring.plugged.in/prometheus"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

TESTS_PASSED=0
TESTS_FAILED=0

# Function to test that authentication is REJECTED
test_rejection() {
    local test_name="$1"
    local username="$2"
    local password="$3"

    echo -n "Testing: $test_name... "

    if [ -z "$username" ] && [ -z "$password" ]; then
        # No auth test
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$PROMETHEUS_URL/graph")
    else
        # With wrong auth test
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -u "$username:$password" "$PROMETHEUS_URL/graph")
    fi

    # Should get 401 Unauthorized
    if [ "$HTTP_CODE" = "401" ]; then
        echo -e "${GREEN}PASSED${NC} (HTTP $HTTP_CODE - Correctly rejected)"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}FAILED${NC} (Expected 401, got HTTP $HTTP_CODE - SECURITY ISSUE!)"
        ((TESTS_FAILED++))
        return 1
    fi
}

echo "========================================"
echo "Prometheus Authentication Security Test"
echo "========================================"
echo ""
echo "Target: $PROMETHEUS_URL"
echo "Purpose: Verify unauthorized access is BLOCKED"
echo ""

# Test 1: No authentication
test_rejection "No credentials provided" "" ""

# Test 2: Wrong username
test_rejection "Wrong username" "wronguser" "somepassword"

# Test 3: Wrong password
test_rejection "Wrong password" "admin" "wrongpassword123"

# Test 4: Empty password
test_rejection "Empty password" "admin" ""

# Test 5: Empty username
test_rejection "Empty username" "" "password123"

# Test 6: Both wrong
test_rejection "Both credentials wrong" "wronguser" "wrongpass"

# Test 7: Case-sensitive username
test_rejection "Wrong case username" "Admin" "password"

# Test 8: SQL injection attempt
test_rejection "SQL injection attempt" "admin' OR '1'='1" "password"

# Test 9: Common default passwords
test_rejection "Common password (admin)" "admin" "admin"
test_rejection "Common password (password)" "admin" "password"
test_rejection "Common password (123456)" "admin" "123456"

# Test 10: Test different endpoints without auth
echo ""
echo "Testing different Prometheus endpoints WITHOUT auth:"
echo "---------------------------------------------------"

echo -n "Testing /prometheus/api/v1/query... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$PROMETHEUS_URL/api/v1/query?query=up")
if [ "$HTTP_CODE" = "401" ]; then
    echo -e "${GREEN}PASSED${NC} (HTTP $HTTP_CODE - Correctly rejected)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}FAILED${NC} (HTTP $HTTP_CODE - SECURITY ISSUE!)"
    ((TESTS_FAILED++))
fi

echo -n "Testing /prometheus/api/v1/targets... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$PROMETHEUS_URL/api/v1/targets")
if [ "$HTTP_CODE" = "401" ]; then
    echo -e "${GREEN}PASSED${NC} (HTTP $HTTP_CODE - Correctly rejected)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}FAILED${NC} (HTTP $HTTP_CODE - SECURITY ISSUE!)"
    ((TESTS_FAILED++))
fi

echo -n "Testing /prometheus/api/v1/rules... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$PROMETHEUS_URL/api/v1/rules")
if [ "$HTTP_CODE" = "401" ]; then
    echo -e "${GREEN}PASSED${NC} (HTTP $HTTP_CODE - Correctly rejected)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}FAILED${NC} (HTTP $HTTP_CODE - SECURITY ISSUE!)"
    ((TESTS_FAILED++))
fi

echo -n "Testing /prometheus/api/v1/alerts... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$PROMETHEUS_URL/api/v1/alerts")
if [ "$HTTP_CODE" = "401" ]; then
    echo -e "${GREEN}PASSED${NC} (HTTP $HTTP_CODE - Correctly rejected)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}FAILED${NC} (HTTP $HTTP_CODE - SECURITY ISSUE!)"
    ((TESTS_FAILED++))
fi

# Summary
echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo -e "${GREEN}✓ Prometheus is properly protected - unauthorized access is blocked.${NC}"
    echo ""
    echo "NOTE: To test with correct credentials, use:"
    echo "  curl -u admin:YOUR_PASSWORD https://monitoring.plugged.in/prometheus/graph"
    exit 0
else
    echo -e "${RED}✗ SECURITY WARNING: Some tests failed!${NC}"
    echo -e "${RED}✗ Unauthorized access may be possible. Please review configuration.${NC}"
    exit 1
fi
