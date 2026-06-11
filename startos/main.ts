import { sdk } from './sdk'

export const main = sdk.setupMain(async ({ effects }) => {
  console.info('Starting TimeBank!')

  const subcontainer = await sdk.SubContainer.of(
    effects,
    { imageId: 'main' },
    sdk.Mounts.of().mountVolume({
      volumeId: 'main',
      subpath: null,
      mountpoint: '/data',
      readonly: false,
    }),
    'timebank-web',
  )

  return sdk.Daemons.of(effects).addDaemon('primary', {
    subcontainer,
    exec: {
      command: ['/app/docker_entrypoint.sh'],
      env: {
        DATA_DIR: '/data',
      },
    },
    ready: {
      display: 'TimeBank Ready',
      fn: () =>
        sdk.healthCheck.checkPortListening(effects, 80, {
          successMessage: 'TimeBank is ready',
          errorMessage: 'TimeBank is not responding',
        }),
    },
    requires: [],
  })
})
