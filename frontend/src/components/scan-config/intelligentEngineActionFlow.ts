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

export async function runSaveThenBatchValidateAction<TSaveResult, TBatchValidationResult>(options: {
	save: () => Promise<TSaveResult>;
	batchValidate: () => Promise<TBatchValidationResult>;
}): Promise<{
	saveResult: TSaveResult;
	batchValidationResult: TBatchValidationResult;
}> {
	const { saveResult, testResult: batchValidationResult } = await runSaveThenTestAction({
		save: options.save,
		test: options.batchValidate,
	});
	return {
		saveResult,
		batchValidationResult,
	};
}
