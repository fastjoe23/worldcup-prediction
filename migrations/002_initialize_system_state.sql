-- Initialize system_state with default phase
INSERT INTO system_state (id, current_phase) 
VALUES (1, 'START')
ON CONFLICT (id) DO NOTHING;
