#!/bin/bash
echo "=== Running Unit Tests ==="
uv run pytest test/unit/
if [ $? -ne 0 ]; then
    echo "❌ Unit tests failed!"
    exit 1
fi

echo "=== Running Integration Tests ==="
uv run pytest test/integration/
if [ $? -ne 0 ]; then
    echo "❌ Integration tests failed!"
    exit 1
fi

echo "=== Running E2E Tests Individually ==="
for file in test/e2e/test_*.py; do
    echo "Running $file..."
    uv run pytest "$file"
    if [ $? -ne 0 ]; then
        echo "❌ E2E test $file failed!"
        exit 1
    fi
done

echo "✅ All tests completed successfully!"
