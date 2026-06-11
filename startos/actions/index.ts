import { sdk } from '../sdk'

const { Action } = sdk

const API_BASE = 'http://127.0.0.1'

// Reset Parent PIN Action
const resetParentPinAction = Action.withoutInput(
  'reset-parent-pin',
  {
    name: 'Reset Parent PIN',
    description: 'Resets the parent PIN to 1031 and clears all active sessions',
    warning:
      'This will reset the parent PIN to 1031 and log out all active parent sessions. You will need to log in again with PIN 1031 and change it immediately.',
    allowedStatuses: 'only-running',
    group: null,
    visibility: 'enabled',
  },
  async () => {
    try {
      const url = `${API_BASE}/api/admin/reset-pin`
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      const result = await response.json()

      if (response.ok) {
        return {
          version: '1' as const,
          title: 'PIN Reset',
          message:
            'Parent PIN has been reset to 1031. All active sessions have been cleared. Log in and change the PIN in Settings immediately.',
          result: null,
        }
      } else {
        return {
          version: '1' as const,
          title: 'Error',
          message: result.detail || 'Failed to reset PIN',
          result: null,
        }
      }
    } catch (e) {
      return {
        version: '1' as const,
        title: 'Error',
        message: `Failed to reset PIN: ${e}`,
        result: null,
      }
    }
  },
)

export const actions = sdk.Actions.of().addAction(resetParentPinAction)
