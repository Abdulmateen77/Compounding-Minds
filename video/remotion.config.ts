import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
// WebGL in headless Chrome needs the ANGLE renderer.
Config.setChromiumOpenGlRenderer('angle');
Config.setOverwriteOutput(true);
