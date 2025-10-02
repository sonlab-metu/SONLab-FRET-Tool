# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

We take the security of our software seriously. If you discover a security vulnerability, we appreciate your help in disclosing it to us in a responsible manner.

### How to Report

Please report security vulnerabilities by email to:  
**sonlab@.metu.edu.tr**

### What to Include
When reporting a vulnerability, please include:
- A detailed description of the vulnerability
- Steps to reproduce the issue
- Any proof-of-concept code or commands
- The version of the software you're using
- Your contact information (optional)

### Our Commitment
- We will acknowledge receipt of your report within 3 business days
- We will keep you informed about the progress of the vulnerability fix
- We will credit you in our security advisories (unless you prefer to remain anonymous)

## Security Updates

- Security updates are released as patch versions (e.g., 2.0.1, 2.0.2)
- We recommend always using the latest stable release
- Critical security fixes will be backported to previous major versions when feasible

## Security Considerations

### Data Handling
- The SONLab FRET Tool processes image data locally on the user's machine
- No data is automatically sent to external servers
- Users should be cautious when analyzing sensitive or proprietary data

### Dependencies
We regularly update our dependencies to address known vulnerabilities. You can check for outdated or vulnerable dependencies using:

```bash
# For Python dependencies
pip list --outdated
```

### Secure Development Practices
- All code changes are peer-reviewed before merging
- We follow secure coding best practices
- Dependencies are regularly audited for known vulnerabilities

## Security Disclosures

### 2025-10-02: Initial Security Policy
- First version of the security policy published

## Responsible Disclosure

We follow responsible disclosure guidelines. Please:
- Allow us a reasonable amount of time to address the vulnerability before any public disclosure
- Make a good faith effort to avoid privacy violations, data destruction, and service interruptions

## License

This security policy is licensed under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).

---

*Last updated: October 2, 2025*
