import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add project root to sys.path
sys.path.append(os.path.abspath(os.getcwd()))

class TestMonetizationReporting(unittest.TestCase):
    
    def setUp(self):
        # Mock necessary environment variables
        os.environ["AI_VOICEOVER"] = "yes"
        os.environ["AI_CAPTIONS"] = "yes"
        
    @patch("compiler.check_health", return_value={"safe": True, "summary": "OK"})
    @patch("compiler._run_command")
    @patch("compiler._get_video_info")
    @patch("Intelligence_Modules.monetization_brain.MonetizationStrategist.analyze_content")
    def test_respect_brain_high_risk(self, mock_analyze, mock_info, mock_run, mock_health):
        """Verify that a HIGH risk from the brain is NOT overwritten by the compiler."""
        from compiler import compile_with_transitions
        
        # Setup mocks
        mock_info.return_value = {"width": 1080, "height": 1920, "duration": 15.0}
        mock_run.return_value = True
        
        # Brain rejects content
        mock_analyze.return_value = {
            "approved": False,
            "risk_level": "HIGH",
            "verdict": "Low Narrative Density",
            "risk_reason": "Too much silence",
            "editorial_script": "Short script"
        }
        
        with patch("compiler.gemini_captions.generate_caption_direct", return_value="Cool fashion"):
            with patch("compiler._save_sidecar") as mock_sidecar:
                with patch("shutil.move"):
                    with patch("compiler.apply_ferrari_composer"):
                         with patch("compiler.Path"):
                              res, wm = compile_with_transitions("test_input.mp4", "Test Title")
        
        # In compiler.py Stage 10, _save_sidecar is called with data=risk_report
        args, kwargs = mock_sidecar.call_args
        saved_data = kwargs.get('data', {})
        
        self.assertEqual(saved_data.get("risk_level"), "HIGH")
        self.assertEqual(saved_data.get("verdict"), "Low Narrative Density")

    @patch("compiler.check_health", return_value={"safe": True, "summary": "OK"})
    @patch("compiler._run_command")
    @patch("compiler._get_video_info")
    @patch("Intelligence_Modules.monetization_brain.MonetizationStrategist.analyze_content")
    def test_conservative_unknown_risk(self, mock_analyze, mock_info, mock_run, mock_health):
        """Verify that UNKNOWN (Brain Offline) is reported as MEDIUM, not LOW."""
        from compiler import compile_with_transitions
        
        mock_info.return_value = {"width": 1080, "height": 1920, "duration": 15.0}
        mock_run.return_value = True
        
        # Brain fails (Offline/Quota)
        mock_analyze.return_value = {
            "approved": False,
            "risk_level": "UNKNOWN",
            "verdict": "Rejected (System Failure)",
            "risk_reason": "Brain offline"
        }
        
        with patch("compiler.gemini_captions.generate_caption_direct", return_value="Cool fashion"):
            with patch("compiler._save_sidecar") as mock_sidecar:
                with patch("shutil.move"):
                    with patch("compiler.apply_ferrari_composer"):
                        with patch("compiler.Path"):
                            compile_with_transitions("test_input.mp4", "Test Title")
        
        args, kwargs = mock_sidecar.call_args
        saved_data = kwargs.get('data', {})
        
        self.assertEqual(saved_data.get("risk_level"), "MEDIUM")
        self.assertEqual(saved_data.get("verdict"), "CHECK REQUIRED (Brain Offline)")

if __name__ == "__main__":
    unittest.main()
