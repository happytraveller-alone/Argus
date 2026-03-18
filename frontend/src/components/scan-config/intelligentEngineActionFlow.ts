export async function runSaveThenTestAction<TSaveResult, TTestResult>(options: {
	save: () => Promise<TSaveResult>;
	test: () => Promise<TTestResult>;
}): Promise<{
	saveResult: TSaveResult;
	testResult: TTestResult;
}> {
	const saveResult = await options.save();
	const testResult = await options.test();
	return {
		saveResult,
		testResult,
	};
}
