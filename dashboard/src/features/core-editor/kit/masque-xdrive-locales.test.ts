import { defineLocaleKeySuite } from './locale-key-scan.test-support'

defineLocaleKeySuite('MASQUE and XDrive', /^coreEditor\.(masque|xdrive|streamForms)\./, ['coreEditor.masque.addressPool', 'coreEditor.xdrive.segmentBytes', 'coreEditor.streamForms.invalidInputs'])
