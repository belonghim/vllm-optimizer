import sys
sys.path.insert(0, '/home/user/projects/vllm-optimizer')

try:
    from backend.main import app
    print("=== Registered Routes ===")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f"{list(route.methods)} {route.path}")
    print("\n=== End of Routes ===")
except Exception as e:
    print(f"Error importing app: {e}")
    import traceback
    traceback.print_exc()
