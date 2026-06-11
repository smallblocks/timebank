import { setupManifest } from '@start9labs/start-sdk'

export const manifest = setupManifest({
  id: 'timebank',
  title: 'TimeBank',
  license: 'MIT',
  wrapperRepo: 'https://github.com/smallblocks/timebank',
  upstreamRepo: 'https://github.com/smallblocks/timebank',
  supportSite: 'https://github.com/smallblocks/timebank/issues',
  marketingSite: 'https://github.com/smallblocks/timebank',
  donationUrl: null,
  docsUrl: 'https://github.com/smallblocks/timebank#readme',
  description: {
    short: 'Do your tasks. Earn your minutes.',
    long: `Family task board. Kids complete tasks and earn screen-time minutes; parents sign off from any device and grant requests with a tap. The bank, the rules, and the receipts all live on your server.`,
  },
  volumes: ['main'],
  images: {
    main: {
      source: { dockerTag: 'localhost/timebank:latest' },
      arch: ['x86_64', 'aarch64'],
    },
  },
  alerts: {
    install: null,
    update: null,
    uninstall: null,
    restore: null,
    start: null,
    stop: null,
  },
  dependencies: {},
})
