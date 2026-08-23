def production_owner_registry() -> tuple[str, ...]:
    return ("reader_engagement","production_readiness","chapter_checkpoint","contract_records","contract_lifecycle_pointer","writer_execution_authority","writer_reconciliation","staged_artifact","final_artifact","promotion_receipt","web_novel_quality","contract_fulfillment","state_change_authority","memory","novel_state","baseline","writer_admission")

def production_exit_manifest() -> dict:
    return {
        "writer": ("novel_continuation_runner.continue_one_chapter",),
        "promotion": ("novel_continuation_runner.promote_passing_draft",),
        "final_writes": ({"owner":"final_artifact","path":"production/final_chapters","guarded":True}, {"owner":"promotion_receipt","path":"production/runs/status","guarded":True}),
    }

def validate_production_exit_manifest(project_root=None) -> tuple[str, ...]:
    """Mechanical consistency check for guarded production exits."""
    from pathlib import Path
    import ast
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    errors = []
    for group, entries in production_exit_manifest().items():
        for entry in entries:
            if isinstance(entry, str):
                module, symbol = entry.rsplit('.', 1)
                if not module.startswith('creative_os.'):
                    module = 'creative_os.' + module
                path = root / (module.replace('.', '/') + '.py')
                if not path.exists(): errors.append(f'{group}:missing:{entry}'); continue
                tree = ast.parse(path.read_text(encoding='utf-8'))
                names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
                if symbol not in names: errors.append(f'{group}:symbol:{entry}')
    return tuple(errors)
